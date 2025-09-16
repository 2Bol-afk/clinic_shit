from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from patients.models import Patient
from .models import Visit
from django.contrib.auth.models import Group
from dashboard.models import ActivityLog
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
import uuid
from io import BytesIO
import qrcode


@login_required
def scan(request):
    context = {}
    # Prefill code from query param
    if request.method == 'GET':
        code = request.GET.get('code')
        if code:
            context['prefill_code'] = code
            # Allow doctors to use this page only when a code is prefilled (from claim)
            try:
                is_doc = request.user.groups.filter(name='Doctor').exists()
            except Exception:
                is_doc = False
            context['allow_doctor_scan'] = bool(is_doc and code)
    # Expose role flags to the template safely
    try:
        context['is_doctor'] = request.user.groups.filter(name='Doctor').exists()
    except Exception:
        context['is_doctor'] = False
    try:
        context['is_reception'] = request.user.groups.filter(name='Reception').exists()
    except Exception:
        context['is_reception'] = False
    try:
        context['is_lab'] = request.user.groups.filter(name='Laboratory').exists()
    except Exception:
        context['is_lab'] = False
    try:
        context['is_doctor'] = request.user.groups.filter(name='Doctor').exists()
    except Exception:
        context['is_doctor'] = False
    if request.method == 'POST':
        # Receptionist: create patient + QR + account
        if request.POST.get('action') == 'create_patient':
            if not (request.user.is_superuser or request.user.groups.filter(name='Reception').exists()):
                messages.error(request, 'You are not allowed to create patients.')
                return render(request, 'visits/scan.html', context)
            full_name = (request.POST.get('full_name') or '').strip()
            email = (request.POST.get('email') or '').strip()
            contact = (request.POST.get('contact') or '').strip()
            address = (request.POST.get('address') or '').strip()
            age_str = (request.POST.get('age') or '').strip()
            if not full_name or not email:
                context['error'] = 'Full name and email are required to create a patient.'
                return render(request, 'visits/scan.html', context)
            try:
                age = int(age_str) if age_str else 0
            except Exception:
                context['error'] = 'Age must be a number.'
                return render(request, 'visits/scan.html', context)
            # If email already exists, reuse that patient instead of creating duplicate
            existing = Patient.objects.filter(email__iexact=email).first()
            if existing:
                messages.info(request, f'Patient with this email already exists. Using existing record for {existing.full_name}.')
                return redirect(f"/visits/scan/?code={existing.patient_code}")
            with transaction.atomic():
                patient_code = uuid.uuid4().hex[:10].upper()
                # Generate QR image
                qr_img = qrcode.make(patient_code)
                buffer = BytesIO()
                qr_img.save(buffer, format='PNG')
                file_name = f"qr_{patient_code}.png"
                patient = Patient(
                    full_name=full_name,
                    email=email,
                    contact=contact,
                    address=address,
                    age=age,
                    patient_code=patient_code,
                )
                patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                patient.save()
                # Create portal user with temp password
                username = f"p_{patient_code.lower()}"
                temp_password = uuid.uuid4().hex[:12]
                user = User.objects.create_user(username=username, email=email, password=temp_password)
                patient.user = user
                patient.must_change_password = True
                patient.save(update_fields=['user','must_change_password'])
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)
            messages.success(request, f'Patient created. Username: {username}, Temp password: {temp_password}.')
            return redirect(f"/visits/scan/?code={patient.patient_code}")

        code = request.POST.get('patient_code', '').strip()
        service = request.POST.get('service', '').strip()
        # Enforce doctor-only service when logged in as Doctor
        try:
            if request.user.groups.filter(name='Doctor').exists():
                service = 'doctor'
        except Exception:
            pass
        # Group-based gate: allow superusers or users in the matching group
        user = request.user
        user_groups = set(user.groups.values_list('name', flat=True))
        allowed = user.is_superuser or \
            (service == 'reception' and 'Reception' in user_groups) or \
            (service == 'doctor' and 'Doctor' in user_groups) or \
            (service == 'lab' and 'Laboratory' in user_groups) or \
            (service == 'pharmacy' and 'Pharmacy' in user_groups) or \
            (service == 'vaccination' and 'Vaccination' in user_groups)
        if not allowed:
            context['error'] = 'You are not allowed to log this service.'
            return render(request, 'visits/scan.html', context)
        try:
            patient = Patient.objects.get(patient_code=code)
            with transaction.atomic():
                kwargs = {
                    'patient': patient,
                    'service': service,
                    'notes': request.POST.get('notes', ''),
                    'created_by': user,
                }
                # Block starting a new doctor consultation if the doctor has unfinished today
                if service == 'doctor':
                    today = timezone.localdate()
                    if Visit.objects.filter(service='doctor', doctor_user=user, doctor_done=False, timestamp__date=today).exists():
                        context['error'] = 'Finish your current consultation before starting another.'
                        return render(request, 'visits/scan.html', context)
                if service == 'reception':
                    # Department and queue assignment (only for consultation)
                    visit_type = request.POST.get('reception_visit_type')
                    dept = request.POST.get('department') if visit_type == 'consultation' else None
                    if dept:
                        kwargs['department'] = dept
                    qn = request.POST.get('queue_number') if visit_type == 'consultation' else None
                    if qn:
                        kwargs['queue_number'] = int(qn)
                    else:
                        # auto-assign next queue number for today and department (when consultation)
                        if visit_type == 'consultation':
                            today = timezone.localdate()
                            last = (Visit.objects
                                    .filter(service='reception', timestamp__date=today, department=dept)
                                    .order_by('-queue_number')
                                    .first())
                            next_q = (last.queue_number + 1) if last and last.queue_number else 1
                            kwargs['queue_number'] = next_q
                        else:
                            # lab/vaccination: assign queue per type tag (no department)
                            tag = 'Laboratory' if visit_type == 'laboratory' else 'Vaccination'
                            today = timezone.localdate()
                            # count existing reception entries for this type
                            last = (Visit.objects
                                    .filter(service='reception', timestamp__date=today, department='')
                                    .filter(notes__icontains=f'[visit: {tag.lower()}]')
                                    .order_by('-queue_number')
                                    .first())
                            next_q = (last.queue_number + 1) if last and last.queue_number else 1
                            kwargs['queue_number'] = next_q
                    # Tag notes with visit type for lab/vaccination for display and queue prefix logic
                    if visit_type in ('laboratory', 'vaccination'):
                        prefix = '[Visit: Laboratory]' if visit_type == 'laboratory' else '[Visit: Vaccination]'
                        current_notes = kwargs.get('notes', '')
                        if prefix.lower() not in current_notes.lower():
                            kwargs['notes'] = (prefix + ' ' + current_notes).strip()
                elif service == 'doctor':
                    # Enforce arrival verification on claimed reception record when available
                    # If doctor is starting from a claimed ticket, ensure doctor_arrived is True
                    rec_id = request.GET.get('rid') or request.POST.get('rid')
                    if rec_id:
                        try:
                            rec_visit = Visit.objects.get(pk=rec_id, service='reception', claimed_by=user)
                            if not rec_visit.doctor_arrived:
                                context['error'] = 'Please verify patient arrival before starting consultation.'
                                return render(request, 'visits/scan.html', context)
                        except Visit.DoesNotExist:
                            pass
                    kwargs['symptoms'] = request.POST.get('symptoms', '')
                    kwargs['diagnosis'] = request.POST.get('diagnosis', '')
                    kwargs['prescription_notes'] = request.POST.get('prescription_notes', '')
                    kwargs['doctor_user'] = user
                    if request.POST.get('doctor_done') == 'on':
                        kwargs['doctor_done'] = True
                        kwargs['doctor_done_at'] = timezone.now()
                elif service == 'lab':
                    kwargs['lab_tests'] = request.POST.get('lab_tests', '')
                    kwargs['lab_completed'] = request.POST.get('lab_completed') == 'on'
                elif service == 'pharmacy':
                    kwargs['medicines'] = request.POST.get('medicines', '')
                    kwargs['dispensed'] = request.POST.get('dispensed') == 'on'
                elif service == 'vaccination':
                    kwargs['vaccine_type'] = request.POST.get('vaccine_type', '')
                    kwargs['vaccine_dose'] = request.POST.get('vaccine_dose', '')
                    vdate = request.POST.get('vaccination_date')
                    if vdate:
                        kwargs['vaccination_date'] = vdate
                visit = Visit.objects.create(**kwargs)
                # Activity logging
                if service == 'doctor':
                    if visit.prescription_notes:
                        ActivityLog.objects.create(
                            actor=user,
                            verb='Prescribed',
                            description=f"{visit.prescription_notes}",
                            patient=patient,
                        )
                    else:
                        ActivityLog.objects.create(
                            actor=user,
                            verb='Consultation',
                            description=(visit.diagnosis or visit.symptoms or 'Doctor consultation logged'),
                            patient=patient,
                        )
                elif service == 'lab' and visit.lab_tests:
                    ActivityLog.objects.create(
                        actor=user,
                        verb='Lab Update',
                        description=f"Tests: {visit.lab_tests}{' (Completed)' if visit.lab_completed else ''}",
                        patient=patient,
                    )
                elif service == 'pharmacy' and visit.medicines:
                    ActivityLog.objects.create(
                        actor=user,
                        verb='Dispensed',
                        description=f"Medicines: {visit.medicines}",
                        patient=patient,
                    )
                elif service == 'vaccination' and visit.vaccine_type:
                    ActivityLog.objects.create(
                        actor=user,
                        verb='Vaccination',
                        description=f"{visit.vaccine_type} {visit.vaccine_dose}",
                        patient=patient,
                    )
            messages.success(request, 'Visit logged successfully.')
            return redirect('/visits/scan/')
        except Patient.DoesNotExist:
            context['error'] = 'Patient not found'
    # Default for allow_doctor_scan when not GET or no code
    if 'allow_doctor_scan' not in context:
        try:
            is_doc = request.user.groups.filter(name='Doctor').exists()
        except Exception:
            is_doc = False
        context['allow_doctor_scan'] = False if is_doc else True
    return render(request, 'visits/scan.html', context)

# Create your views here.
