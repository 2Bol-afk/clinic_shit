from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Q
from patients.models import Patient, Doctor
from visits.models import Visit, ServiceType, LabResult, Laboratory, VaccinationRecord, VaccinationType
from visits.forms import LabResultForm, VaccinationForm
from django.contrib.auth.models import Group, User
from .models import ActivityLog
from patients.forms import DoctorForm
from django import forms
from django.contrib import messages
from django.core.mail import EmailMessage
from django.conf import settings
from io import BytesIO
from django.core.files.base import ContentFile
import qrcode
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.http import JsonResponse
import re
import csv
import os
from django.core.mail import send_mail
try:
    from openpyxl import Workbook
except Exception:
    Workbook = None


def is_admin(user):
    return user.is_superuser


def is_reception(user):
    return user.is_superuser or user.groups.filter(name='Reception').exists()
@login_required
@user_passes_test(lambda u: u.is_superuser)
def send_test_email(request):
    to = request.GET.get('to') or os.getenv('TEST_EMAIL_TO') or settings.DEFAULT_FROM_EMAIL
    try:
        sent = send_mail(
            subject='SMTP live test',
            message='Hello from Clinic QR System.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            fail_silently=False,
        )
        if sent:
            messages.success(request, f'Email sent successfully to {to}.')
        else:
            messages.warning(request, f'No email was sent to {to}.')
    except Exception as e:
        messages.error(request, f'Email send failed: {e}')
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard_index')

@login_required
def index(request):
    # Redirect to role-specific dashboard if not superuser
    if not request.user.is_superuser:
        gnames = set(request.user.groups.values_list('name', flat=True))
        if 'Reception' in gnames:
            return redirect('dashboard_reception')
        if 'Doctor' in gnames:
            return redirect('dashboard_doctor')
        if 'Laboratory' in gnames:
            return redirect('dashboard_lab')
        if 'Pharmacy' in gnames:
            return redirect('dashboard_pharmacy')
        if 'Vaccination' in gnames:
            return redirect('dashboard_vaccination')
    now = timezone.localdate()
    total_patients = Patient.objects.count()
    patients_served_today = Visit.objects.filter(timestamp__date=now).values('patient').distinct().count()
    per_service = (
        Visit.objects.filter(timestamp__date=now)
        .values('service')
        .order_by()
        .annotate(count=models.Count('id'))
    )
    try:
        doctor_group = Group.objects.get(name='Doctor')
        num_doctors = doctor_group.user_set.count()
    except Group.DoesNotExist:
        num_doctors = 0
    activity_logs = ActivityLog.objects.select_related('actor', 'patient')[:25]
    context = {
        'total_patients': total_patients,
        'patients_served_today': patients_served_today,
        'per_service': per_service,
        'num_doctors': num_doctors,
        'activity_logs': activity_logs,
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def post_login_redirect(request):
    # Patients go to portal; staff to dashboards
    try:
        p = request.user.patient_profile
        if p.must_change_password:
            return redirect('patient_password_first')
        return redirect('patient_portal')
    except AttributeError:
        # User doesn't have a patient profile, check if they're staff
        if request.user.is_superuser:
            return redirect('dashboard_index')
        elif request.user.groups.filter(name='Reception').exists():
            return redirect('dashboard_reception')
        elif request.user.groups.filter(name='Doctor').exists():
            return redirect('dashboard_doctor')
        elif request.user.groups.filter(name='Laboratory').exists():
            return redirect('dashboard_lab')
        elif request.user.groups.filter(name='Pharmacy').exists():
            return redirect('dashboard_pharmacy')
        elif request.user.groups.filter(name='Vaccination').exists():
            return redirect('dashboard_vaccination')
        else:
            # Default fallback
            return redirect('dashboard_reception')
    except Exception as e:
        # Log the error for debugging
        print(f"Post-login redirect error: {e}")
        return redirect('dashboard_reception')


@login_required
def reception_dashboard(request):
    today = timezone.localdate()
    visits = (Visit.objects
              .filter(service='reception', timestamp__date=today)
              .select_related('patient', 'created_by')
              .order_by('-timestamp'))
    
    # Handle patient email from QR scan
    patient_email = request.GET.get('patient_email', '').strip()
    patient_data = None
    if patient_email:
        try:
            from patients.models import Patient
            patient = Patient.objects.get(email=patient_email)
            patient_data = {
                'id': patient.id,
                'full_name': patient.full_name,
                'patient_code': patient.patient_code,
                'email': patient.email,
            }
        except Patient.DoesNotExist:
            pass
    
    return render(
        request,
        'dashboard/reception.html',
        {
            'visits': visits,
            'today': today,
                'patient_data': patient_data,
        },
    )


class WalkInForm(forms.Form):
    full_name = forms.CharField(max_length=255)
    age = forms.IntegerField(min_value=0)
    address = forms.CharField(widget=forms.Textarea)
    contact = forms.CharField(max_length=50)
    email = forms.EmailField()
    reception_visit_type = forms.ChoiceField(choices=[('consultation','Consultation'),('laboratory','Laboratory'),('vaccination','Vaccination')])
    department = forms.ChoiceField(choices=Visit.Department.choices, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' ' + css).strip()


@login_required
@user_passes_test(is_reception)
def reception_walkin(request):
    if request.method == 'POST':
        form = WalkInForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            # Reuse existing patient by email if exists
            existing = Patient.objects.filter(email__iexact=data['email']).first()
            patient = existing
            if not existing:
                # Create patient with generated patient_code and minimal fields
                import uuid
                patient_code = uuid.uuid4().hex[:10].upper()
                patient = Patient.objects.create(
                    full_name=data['full_name'],
                    age=data['age'],
                    address=data['address'],
                    contact=data['contact'],
                    email=data['email'],
                    patient_code=patient_code,
                )
                # Generate QR with email + patient id
                try:
                    qr_payload = f"email:{patient.email};id:{patient.id}"
                    qr_img = qrcode.make(qr_payload)
                    buffer = BytesIO()
                    qr_img.save(buffer, format='PNG')
                    file_name = f"qr_{patient.patient_code}.png"
                    patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                    patient.save(update_fields=['qr_code'])
                except Exception:
                    buffer = None
                    file_name = None
                # Create portal user with temp password and force change
                try:
                    temp_password = uuid.uuid4().hex[:12]
                    username = f"p_{patient.patient_code.lower()}"
                    user = User.objects.create_user(username=username, email=patient.email, password=temp_password)
                    patient.user = user
                    patient.must_change_password = True
                    patient.save(update_fields=['user','must_change_password'])
                    group, _ = Group.objects.get_or_create(name='Patient')
                    user.groups.add(group)
                except Exception:
                    temp_password = None
            else:
                # Ensure existing patient has a QR; generate if missing
                buffer = None
                file_name = None
                if not existing.qr_code:
                    try:
                        qr_payload = f"email:{existing.email};id:{existing.id}"
                        qr_img = qrcode.make(qr_payload)
                        buffer = BytesIO()
                        qr_img.save(buffer, format='PNG')
                        file_name = f"qr_{existing.patient_code}.png"
                        existing.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                        existing.save(update_fields=['qr_code'])
                    except Exception:
                        buffer = None
                        file_name = None
                # If existing patient has no portal user, create temp credentials
                temp_password = None
                if not existing.user:
                    try:
                        import uuid as _uuid
                        temp_password = _uuid.uuid4().hex[:12]
                        username = f"p_{existing.patient_code.lower()}"
                        user = User.objects.create_user(username=username, email=existing.email, password=temp_password)
                        existing.user = user
                        existing.must_change_password = True
                        existing.save(update_fields=['user','must_change_password'])
                        group, _ = Group.objects.get_or_create(name='Patient')
                        user.groups.add(group)
                    except Exception:
                        temp_password = None
            # Create reception visit
            visit_type = data['reception_visit_type']
            kwargs = {
                'patient': patient,
                'service': 'reception',
                'created_by': request.user,
                'status': Visit.Status.QUEUED,
                'department': '',
            }
            today = timezone.localdate()
            if visit_type == 'consultation':
                dept = data.get('department') or ''
                kwargs['department'] = dept
                last = (Visit.objects
                        .filter(service='reception', timestamp__date=today, department=dept)
                        .order_by('-queue_number')
                        .first())
                next_q = (last.queue_number + 1) if last and last.queue_number else 1
                kwargs['queue_number'] = next_q
            else:
                tag = 'Laboratory' if visit_type == 'laboratory' else 'Vaccination'
                last = (Visit.objects
                        .filter(service='reception', timestamp__date=today, department='')
                        .filter(notes__icontains=f'[visit: {tag.lower()}]')
                        .order_by('-queue_number')
                        .first())
                next_q = (last.queue_number + 1) if last and last.queue_number else 1
                kwargs['queue_number'] = next_q
                prefix = '[Visit: Laboratory]' if visit_type == 'laboratory' else '[Visit: Vaccination]'
                kwargs['notes'] = prefix
                # Set service_type as hint
                svc_name = 'Laboratory' if visit_type == 'laboratory' else 'Vaccination'
                svc = ServiceType.objects.filter(name__iexact=svc_name).first()
                if svc:
                    kwargs['service_type'] = svc
            Visit.objects.create(**kwargs)
            # Email confirmation with QR attachment (explicit feedback)
            try:
                if patient.email:
                    body_parts = [
                        f"Dear {patient.full_name},\n",
                        "\nThank you for registering with Clinic QR System.\n",
                        f"Your Patient Code is: {patient.patient_code}\n",
                    ]
                    if 'temp_password' in locals() and temp_password:
                        body_parts.append(f"Temporary Password: {temp_password}\n")
                        body_parts.append("\nPlease log in using the temporary password and change it on your first login.\n")
                    body_parts.append("\nPlease keep this email for future reference.\n")
                    body_parts.append("You can use the attached QR code for faster check-in at the reception.\n\n")
                    body_parts.append("Regards,\nClinic QR System")
                    body = ''.join(body_parts)
                    email = EmailMessage(
                        subject='Your Patient QR Code and Registration Details',
                        body=body,
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None) or None,
                        to=[patient.email],
                    )
                    if (patient.qr_code and hasattr(patient.qr_code, 'path')):
                        try:
                            with open(patient.qr_code.path, 'rb') as f:
                                email.attach(f"qr_{patient.patient_code}.png", f.read(), 'image/png')
                        except Exception:
                            pass
                    elif buffer:
                        email.attach(file_name or 'qr.png', (buffer.getvalue() if buffer else b''), 'image/png')
                    sent_count = email.send(fail_silently=False)
                    if sent_count:
                        messages.success(request, f'Confirmation email sent to {patient.email}.')
                    else:
                        messages.warning(request, f'Confirmation email not sent to {patient.email}.')
            except Exception as e:
                messages.error(request, f'Email send failed: {e}')
            messages.success(request, 'Walk-in patient registered and queued.')
            return redirect('dashboard_reception')
    else:
        form = WalkInForm()
    return render(request, 'dashboard/reception_walkin.html', {'form': form})


@login_required
@user_passes_test(is_reception)
def reception_edit(request, pk: int):
    visit = get_object_or_404(Visit, pk=pk, service='reception')
    if request.method == 'POST':
        visit_type = request.POST.get('reception_visit_type')
        if visit_type == 'consultation':
            visit.department = request.POST.get('department') or ''
            qn = request.POST.get('queue_number')
            visit.queue_number = int(qn) if qn else visit.queue_number
        else:
            # For laboratory/vaccination, clear department and queue number
            visit.department = ''
            visit.queue_number = None
        visit.notes = request.POST.get('notes', visit.notes)
        visit.save()
        messages.success(request, 'Reception entry updated.')
        return redirect('dashboard_reception')
    return render(request, 'dashboard/reception_edit.html', {'visit': visit})


@login_required
@user_passes_test(is_reception)
def reception_delete(request, pk: int):
    visit = get_object_or_404(Visit, pk=pk, service='reception')
    if request.method == 'POST':
        visit.delete()
        messages.success(request, 'Reception entry deleted.')
        return redirect('dashboard_reception')
    return render(request, 'dashboard/reception_delete_confirm.html', {'visit': visit})


@login_required
def doctor_dashboard(request):
    today = timezone.localdate()
    # Show only this doctor's consultations if user is a Doctor; admins see all
    base_qs = Visit.objects.filter(service='doctor', timestamp__date=today)
    if request.user.groups.filter(name='Doctor').exists():
        base_qs = base_qs.filter(doctor_user=request.user)
    recent = base_qs.select_related('patient', 'created_by').order_by('-timestamp')[:5]
    # Timeline for this doctor if user is a doctor
    timeline = Visit.objects.none()
    waiting = Visit.objects.none()
    claimed_waiting = Visit.objects.none()
    verified_claimed = Visit.objects.none()
    not_done = Visit.objects.none()
    unfinished = Visit.objects.filter(service='doctor', doctor_user=request.user, doctor_done=False, timestamp__date=today).exists()
    if request.user.groups.filter(name='Doctor').exists():
        # Determine doctor's department (specialization)
        try:
            dept = request.user.doctor_profile.specialization
        except Doctor.DoesNotExist:
            dept = None
        # Waiting list: today's reception unclaimed; filter by department if available
        q = Visit.objects.filter(service='reception', timestamp__date=today, claimed_by__isnull=True)
        if dept:
            q = q.filter(department=dept)
        waiting = q.select_related('patient').order_by('queue_number', 'timestamp')
        claimed_waiting = (Visit.objects
                           .filter(service='reception', timestamp__date=today, claimed_by=request.user, doctor_arrived=False)
                           .select_related('patient')
                           .order_by('timestamp'))
        # Verified claimed arrivals ready to consult by status
        verified_claimed = (Visit.objects
                            .filter(service='reception', timestamp__date=today, claimed_by=request.user, doctor_status='ready_to_consult')
                            .select_related('patient')
                            .order_by('timestamp'))
        # Not Done = your in-progress doctor drafts for today
        not_done = (Visit.objects
                    .filter(service='doctor', doctor_user=request.user, doctor_done=False, timestamp__date=today)
                    .select_related('patient')
                    .order_by('-timestamp'))
        timeline = Visit.objects.filter(doctor_user=request.user).select_related('patient').order_by('-timestamp')[:5]
    return render(request, 'dashboard/doctor.html', {
        'visits': recent,
        'today': today,
        'timeline': timeline,
        'waiting': waiting,
        'claimed_waiting': claimed_waiting,
        'verified_claimed': verified_claimed,
        'not_done': not_done,
        'unfinished': unfinished,
    })


@login_required
def lab_dashboard(request):
    # Show pending lab requests - prefer reception-tagged Lab arrivals
    today = timezone.localdate()
    # Only exclude patients already in an active lab workflow (In Process) today
    already_in_lab = (Visit.objects
                      .filter(service='lab', status=Visit.Status.IN_PROCESS, timestamp__date=today)
                      .values_list('patient_id', flat=True))
    # Reception tickets queued for laboratory (service_type = Lab) in queue order
    base_reception_lab = (Visit.objects
                          .filter(service='reception', timestamp__date=today)
                          .filter(Q(service_type__name__iexact='Laboratory') | Q(notes__icontains='[visit: laboratory]')))
    # Queued tickets not yet claimed (be tolerant of empty/legacy status)
    unclaimed = (base_reception_lab
                 .filter(Q(status=Visit.Status.QUEUED) | Q(status__isnull=True) | Q(status=''))
                 .filter(lab_claimed_by__isnull=True)
                 .order_by('queue_number', 'timestamp'))
    # Claimed tickets waiting to arrive for the current lab user (or any if superuser)
    claimed_filter = Q(status=Visit.Status.CLAIMED, lab_arrived=False)
    if not request.user.is_superuser:
        claimed_filter &= Q(lab_claimed_by=request.user)
    claimed_waiting = base_reception_lab.filter(claimed_filter).order_by('queue_number', 'timestamp')
    # Categorize lab workflow states using ONLY the latest LabResult per visit for today
    from django.db.models import OuterRef, Subquery, F
    latest_ts_sq = (LabResult.objects
                    .filter(visit=OuterRef('visit'))
                    .order_by('-updated_at')
                    .values('updated_at')[:1])
    lab_results_today = (LabResult.objects
                         .select_related('visit__patient')
                         .filter(visit__timestamp__date=today)
                         .annotate(latest_updated_at=Subquery(latest_ts_sq))
                         .filter(updated_at=F('latest_updated_at')))
    ready = lab_results_today.filter(status='queue').order_by('visit__queue_number', 'visit__timestamp')
    in_process = lab_results_today.filter(status='in_process').order_by('-updated_at')
    not_done = lab_results_today.filter(status='not_done').order_by('-updated_at')
    completed = lab_results_today.filter(status='done').order_by('-updated_at')[:20]
    # Provide lab department choices from ServiceType model (fallback to defaults)
    lab_service_types = list(ServiceType.objects.filter(is_active=True).order_by('name'))
    if not lab_service_types:
        # Fallback list if no ServiceType rows
        default = [
            ('Hematology', 'Hematology (Blood Analysis)'),
            ('Clinical Microscopy', 'Clinical Microscopy (Urine/Stool Exam)'),
            ('Clinical Chemistry', 'Clinical Chemistry (Blood Chemistry)'),
            ('Immunology and Serology', 'Immunology and Serology (Infectious Disease Tests)'),
            ('Microbiology', 'Microbiology (Culture and Sensitivity)'),
            ('Pathology', 'Pathology (Tissue and Biopsy)'),
        ]
        lab_service_types = [type('Svc', (), {'name': n, 'description': d}) for (n, d) in default]
    return render(request, 'dashboard/lab.html', {
        'pending_unclaimed': unclaimed,
        'pending_claimed': claimed_waiting,
        'ready': ready,
        'in_process': in_process,
        'not_done': not_done,
        'completed': completed,
        'lab_service_types': lab_service_types,
        'lab_types': Laboratory.choices,
        'lab_type_labels': dict(Laboratory.choices),
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
@require_POST
def lab_claim(request):
    rec_id = request.POST.get('reception_visit_id')
    visit = get_object_or_404(Visit, pk=rec_id, service='reception')
    # Only one lab claim per ticket; allow re-claim to the same user
    if visit.lab_claimed_by and visit.lab_claimed_by != request.user:
        messages.error(request, 'This ticket is already claimed by another staff.')
        return redirect('dashboard_lab')
    visit.lab_claimed_by = request.user
    visit.lab_claimed_at = timezone.now()
    visit.status = Visit.Status.CLAIMED
    visit.save(update_fields=['lab_claimed_by', 'lab_claimed_at', 'status'])
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': 'Claimed', 'patient_id': visit.patient_id})
    messages.success(request, 'Ticket claimed. Verify QR on arrival, then receive to start.')
    return redirect('dashboard_lab')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
@require_POST
def lab_receive(request):
    # Receive into lab queue from either reception-tagged arrival or doctor request
    rec_id = request.POST.get('reception_visit_id')
    doc_id = request.POST.get('doctor_visit_id')
    if rec_id:
        src = get_object_or_404(Visit, pk=rec_id, service='reception')
        src_type = 'reception'
    else:
        src = get_object_or_404(Visit, pk=doc_id, service='doctor')
        src_type = 'doctor'
    with transaction.atomic():
        # If coming from reception, enforce that it has been claimed by someone in Laboratory
        if src_type == 'reception':
            if not src.lab_claimed_by:
                messages.error(request, 'Please claim this ticket first, then verify QR on arrival.')
                return redirect('dashboard_lab')
        # If coming from reception, verify identity via QR code or email
        if rec_id:
            verify_code = (request.POST.get('verify_code') or '').strip()
            patient_email = (request.POST.get('patient_email') or '').strip()
            if not verify_code and not patient_email:
                messages.error(request, 'Please verify patient on arrival (scan QR or enter email).')
                return redirect('dashboard_lab')
            if patient_email:
                try:
                    p = Patient.objects.get(email=patient_email)
                except Patient.DoesNotExist:
                    messages.error(request, 'Patient not found for the provided email.')
                    return redirect('dashboard_lab')
                if src.patient_id != p.id:
                    messages.error(request, 'Provided email does not match the expected patient for this ticket.')
                    return redirect('dashboard_lab')
            elif verify_code:
                if getattr(src.patient, 'patient_code', '').strip().upper() != verify_code.strip().upper():
                    messages.error(request, 'QR/Patient code does not match the expected patient for this ticket.')
                    return redirect('dashboard_lab')
            # Mark arrival on the reception record
            if not src.lab_arrived:
                src.lab_arrived = True
                src.status = Visit.Status.CLAIMED
                src.save(update_fields=['lab_arrived', 'status'])
        # Carry over queue number for reception-tagged lab arrivals
        qn = src.queue_number if (src_type == 'reception' and src.queue_number) else None
        test_type = request.POST.get('lab_test_type', '').strip()
        svc = None
        if test_type:
            svc = ServiceType.objects.filter(name=test_type).first()
        new_visit = Visit.objects.create(
            patient=src.patient,
            service='lab',
            notes=(f"Received for lab. From {src_type} #{src.id}."),
            lab_tests=(src.lab_tests if hasattr(src, 'lab_tests') else '') or (src.prescription_notes if hasattr(src, 'prescription_notes') else ''),
            lab_test_type=test_type,
            service_type=svc,
            queue_number=qn,
            created_by=request.user,
        )
        # Seed LabResult for this lab visit and set its workflow state
        lr_status = 'in_process' if test_type else 'queue'
        LabResult.objects.create(
            visit=new_visit,
            lab_type=(test_type or (svc.name if svc else Laboratory.HEMATOLOGY)),
            status=lr_status,
            results={},
        )
        # Move Visit into in-process immediately when a test type is set
        if test_type:
            new_visit.status = Visit.Status.IN_PROCESS
            new_visit.assigned_to = request.user
            new_visit.save(update_fields=['status', 'assigned_to'])
            # Mirror doctor: mark linked reception ticket In Process for visibility
            if rec_id:
                src.status = Visit.Status.IN_PROCESS
                src.save(update_fields=['status'])
        ActivityLog.objects.create(
            actor=request.user,
            verb='Lab Receive',
            description=f"Received tests: {(src.lab_tests if hasattr(src, 'lab_tests') else '') or (src.prescription_notes if hasattr(src, 'prescription_notes') else '')}",
            patient=src.patient,
        )
    # Support AJAX for dynamic UI updates
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Patient moved to In Process.' if test_type else 'Patient moved to Ready for Lab Processing.',
            'status': lr_status,
            'patient_id': new_visit.patient_id,
            'lab_visit_id': new_visit.id,
        })
    if test_type:
        messages.success(request, 'Patient moved to In Process.')
    else:
        messages.success(request, 'Patient moved to Ready for Lab Processing.')
    return redirect('dashboard_lab')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
@require_POST
def lab_mark_done(request, pk: int):
    lab_visit = get_object_or_404(Visit, pk=pk, service='lab', lab_completed=False)
    with transaction.atomic():
        # Accept updated results before completion
        lab_visit.lab_results = request.POST.get('lab_results', lab_visit.lab_results)
        lab_visit.lab_completed = True
        lab_visit.lab_completed_at = timezone.now()
        lab_visit.notes = request.POST.get('notes', lab_visit.notes)
        lab_visit.status = Visit.Status.DONE
        lab_visit.save(update_fields=['lab_results', 'lab_completed', 'lab_completed_at', 'notes', 'status'])
        # Also mark associated LabResult as done
        lr = LabResult.objects.filter(visit=lab_visit).order_by('-updated_at').first()
        if lr and lr.status != 'done':
            lr.status = 'done'
            lr.save(update_fields=['status'])
        # Reflect completion on the specific reception ticket that spawned this lab visit
        rec = None
        try:
            m = re.search(r"From\s+reception\s+#(\d+)", lab_visit.notes or '', flags=re.IGNORECASE)
            if m:
                rec_id = int(m.group(1))
                rec = Visit.objects.filter(pk=rec_id, service='reception').first()
        except Exception:
            rec = None
        if not rec:
            # Fallback: latest today's reception for this patient
            today = timezone.localdate()
            rec = (Visit.objects
                   .filter(service='reception', patient=lab_visit.patient, timestamp__date=today)
                   .order_by('-timestamp')
                   .first())
        if rec:
            rec.status = Visit.Status.DONE
            rec.save(update_fields=['status'])
        # Additionally, mark any same-day reception LAB tickets as done for this patient
        today = timezone.localdate()
        (Visit.objects
         .filter(service='reception', patient=lab_visit.patient, timestamp__date=today)
         .filter(Q(notes__icontains='[visit: laboratory]') | Q(service_type__name__iexact='Laboratory'))
         .exclude(status=Visit.Status.DONE)
         .update(status=Visit.Status.DONE))
        ActivityLog.objects.create(
            actor=request.user,
            verb='Lab Completed',
            description=f"Completed tests: {lab_visit.lab_tests or ''}{(' · Results: '+lab_visit.lab_results) if lab_visit.lab_results else ''}",
            patient=lab_visit.patient,
        )
    messages.success(request, 'Marked as done.')
    return redirect('dashboard_lab')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
def lab_results_demo(request):
    return render(request, 'dashboard/lab_results_demo.html')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
@require_POST
def lab_verify_email(request):
    try:
        rec_id = int(request.POST.get('reception_visit_id') or '0')
    except Exception:
        rec_id = 0
    email = (request.POST.get('patient_email') or '').strip()
    if not rec_id or not email:
        return JsonResponse({'success': False, 'message': 'Missing visit or email.'}, status=400)
    visit = Visit.objects.filter(pk=rec_id, service='reception').select_related('patient').first()
    if not visit:
        return JsonResponse({'success': False, 'message': 'Reception visit not found.'}, status=404)
    if not visit.patient or visit.patient.email.strip().lower() != email.strip().lower():
        return JsonResponse({'success': False, 'message': 'Email does not match this patient.'}, status=400)
    return JsonResponse({'success': True})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
def lab_work(request, pk: int):
    lab_visit = get_object_or_404(Visit, pk=pk, service='lab')
    if request.method == 'POST':
        # Collect discrete fields and combine into a single stored text
        parts = []
        for key in ['result_1','result_2','result_3','result_4','result_5']:
            val = request.POST.get(key, '').strip()
            if val:
                parts.append(val)
        interp = request.POST.get('interpretation', '').strip()
        if interp:
            parts.append(f"Interpretation: {interp}")
        lab_visit.lab_results = "\n".join(parts) if parts else ''
        # Handle mark not done vs complete
        mark_not_done = request.POST.get('mark_not_done') == '1'
        if request.POST.get('complete') == '1':
            lab_visit.lab_completed = True
            lab_visit.lab_completed_at = timezone.now()
            # Remove not-done tag if present
            if lab_visit.notes:
                lab_visit.notes = lab_visit.notes.replace('[Lab: Not Done]', '').strip()
        else:
            lab_visit.lab_completed = False
            if mark_not_done:
                tag = '[Lab: Not Done]'
                current = lab_visit.notes or ''
                if tag.lower() not in current.lower():
                    lab_visit.notes = (current + (' ' if current else '') + tag).strip()
        # Keep LabResult status in sync with this workflow
        lr = LabResult.objects.filter(visit=lab_visit).order_by('-updated_at').first()
        if not lr:
            lr = LabResult.objects.create(
                visit=lab_visit,
                lab_type=(lab_visit.lab_test_type or Laboratory.HEMATOLOGY),
            )
        # Default to in-process when saving without completion/not-done
        action = 'save'
        if request.POST.get('complete') == '1':
            action = 'done'
        elif mark_not_done:
            action = 'not_done'
        # Persist visit + labresult statuses
        if action == 'done':
            lab_visit.status = Visit.Status.DONE
            lab_visit.save()
            lr.status = 'done'
            lr.save(update_fields=['status'])
            # Reflect completion on today's matching reception ticket
            today = timezone.localdate()
            rec = (Visit.objects
                   .filter(service='reception', patient=lab_visit.patient, timestamp__date=today)
                   .order_by('-timestamp')
                   .first())
            if rec:
                rec.status = Visit.Status.DONE
                rec.save(update_fields=['status'])
            messages.success(request, 'Marked as Done.')
            return redirect('dashboard_lab')
        elif action == 'not_done':
            lab_visit.status = Visit.Status.IN_PROCESS
            lab_visit.save()
            lr.status = 'not_done'
            lr.save(update_fields=['status'])
            messages.success(request, 'Marked as Not Done.')
            return redirect('dashboard_lab')
        else:
            lab_visit.status = Visit.Status.IN_PROCESS
            lab_visit.save()
            lr.status = 'in_process'
            lr.save(update_fields=['status'])
            messages.success(request, 'Lab work saved.')
            return redirect('lab_work', pk=lab_visit.id)
    # Prefill discrete inputs from stored text (best-effort)
    prefill = {'result_1':'','result_2':'','result_3':'','result_4':'','result_5':'','interpretation':''}
    if lab_visit.lab_results:
        lines = [ln for ln in lab_visit.lab_results.split('\n') if ln.strip()]
        for i in range(min(5, len(lines))):
            if lines[i].lower().startswith('interpretation:'):
                prefill['interpretation'] = lines[i].split(':',1)[1].strip()
            else:
                prefill[f'result_{i+1}'] = lines[i]
        # If interpretation appears later
        for ln in lines:
            if ln.lower().startswith('interpretation:'):
                prefill['interpretation'] = ln.split(':',1)[1].strip()
                break
    return render(request, 'dashboard/lab_work.html', {'v': lab_visit, 'prefill': prefill})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
def lab_result_work(request, pk: int):
    # pk refers to a lab Visit
    lab_visit = get_object_or_404(Visit, pk=pk, service='lab')
    # Get or create a LabResult entry tied to this visit
    lr = LabResult.objects.filter(visit=lab_visit).order_by('-updated_at').first()
    if not lr:
        lr = LabResult.objects.create(visit=lab_visit, lab_type=(lab_visit.lab_test_type or Laboratory.HEMATOLOGY))
    if request.method == 'POST':
        form = LabResultForm(request.POST, instance=lr, initial={'lab_type': lr.lab_type})
        if form.is_valid():
            lr.lab_type = form.cleaned_data['lab_type']
            new_results = form.to_results_json()
            # Preserve previously entered results if nothing was submitted (e.g., marking Not Done without changes)
            if not new_results:
                new_results = lr.results or {}
            lr.results = new_results
            action = request.POST.get('action')
            if action == 'done':
                lr.status = 'done'
                lab_visit.status = Visit.Status.DONE
                lab_visit.lab_completed = True
                lab_visit.lab_completed_at = timezone.now()
                lab_visit.save(update_fields=['status','lab_completed','lab_completed_at'])
                # Reflect completion on the specific reception ticket that spawned this lab visit
                rec = None
                try:
                    m = re.search(r"From\s+reception\s+#(\d+)", lab_visit.notes or '', flags=re.IGNORECASE)
                    if m:
                        rec_id = int(m.group(1))
                        rec = Visit.objects.filter(pk=rec_id, service='reception').first()
                except Exception:
                    rec = None
                if not rec:
                    today = timezone.localdate()
                    rec = (Visit.objects
                           .filter(service='reception', patient=lab_visit.patient, timestamp__date=today)
                           .order_by('-timestamp')
                           .first())
                if rec:
                    rec.status = Visit.Status.DONE
                    rec.save(update_fields=['status'])
                # Additionally, mark any same-day reception LAB tickets as done for this patient
                (Visit.objects
                 .filter(service='reception', patient=lab_visit.patient, timestamp__date=timezone.localdate())
                 .filter(Q(notes__icontains='[visit: laboratory]') | Q(service_type__name__iexact='Laboratory'))
                 .exclude(status=Visit.Status.DONE)
                 .update(status=Visit.Status.DONE))
            elif action == 'not_done':
                lr.status = 'not_done'
            else:
                lr.status = 'in_process'
                lab_visit.status = Visit.Status.IN_PROCESS
                lab_visit.save(update_fields=['status'])
            lr.save()
            messages.success(request, 'Lab result saved.')
            return redirect('dashboard_lab')
    else:
        form = LabResultForm(instance=lr, initial={'lab_type': lr.lab_type})
    return render(request, 'dashboard/lab_result_work.html', {'visit': lab_visit, 'form': form, 'lab_result': lr})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Laboratory').exists())
@require_POST
def lab_set_department(request, pk: int):
    # Set the laboratory department (test type) for a lab visit
    lab_visit = get_object_or_404(Visit, pk=pk, service='lab', lab_completed=False)
    test_type = (request.POST.get('lab_test_type') or '').strip()
    lab_visit.lab_test_type = test_type
    svc = ServiceType.objects.filter(name=test_type).first() if test_type else None
    lab_visit.service_type = svc
    lab_visit.save(update_fields=['lab_test_type', 'service_type'])
    messages.success(request, 'Patient moved to In Process.')
    return redirect('dashboard_lab')


@login_required
def pharmacy_dashboard(request):
    # Show prescriptions from doctor
    prescriptions = (Visit.objects
                     .filter(service='doctor')
                     .exclude(prescription_notes='')
                     .order_by('-timestamp'))
    dispensed = (Visit.objects
                 .filter(service='pharmacy')
                 .order_by('-timestamp')[:50])
    return render(request, 'dashboard/pharmacy.html', {'prescriptions': prescriptions, 'dispensed': dispensed})


@login_required
def vaccination_dashboard(request):
    # Vaccination dashboard mirrors Lab flow
    today = timezone.localdate()
    # Reception tickets tagged for vaccination
    base_reception_vacc = (Visit.objects
                           .filter(service='reception', timestamp__date=today)
                           .filter(Q(service_type__name__iexact='Vaccination') | Q(notes__icontains='[visit: vaccination]')))
    # Unclaimed queue
    unclaimed = (base_reception_vacc
                 .filter(Q(status=Visit.Status.QUEUED) | Q(status__isnull=True) | Q(status=''))
                 .filter(assigned_to__isnull=True)
                 .order_by('queue_number', 'timestamp'))
    # Claimed waiting to arrive (claimed but not received yet)
    # Exclude only reception tickets that were already RECEIVED into vaccination today
    received_from_reception_ids: set[int] = set()
    _vacc_visits = (Visit.objects
                    .filter(service='vaccination', timestamp__date=today)
                    .values('id', 'notes'))
    for _v in _vacc_visits:
        try:
            m = re.search(r"From\s+reception\s+#(\d+)", _v.get('notes') or '', flags=re.IGNORECASE)
            if m:
                received_from_reception_ids.add(int(m.group(1)))
        except Exception:
            pass
    claimed_filter = Q(status=Visit.Status.CLAIMED)
    if not request.user.is_superuser:
        claimed_filter &= Q(assigned_to=request.user)
    claimed_waiting = (base_reception_vacc
                       .filter(claimed_filter)
                       .exclude(id__in=list(received_from_reception_ids))
                       .order_by('queue_number', 'timestamp'))
    
    # Debug: Print some info about the filtering
    print(f"DEBUG - Today: {today}")
    print(f"DEBUG - Base reception vacc count: {base_reception_vacc.count()}")
    print(f"DEBUG - Received from reception IDs: {sorted(received_from_reception_ids)}")
    print(f"DEBUG - Claimed waiting count: {claimed_waiting.count()}")
    print(f"DEBUG - User: {request.user}, Is superuser: {request.user.is_superuser}")
    for v in claimed_waiting:
        print(f"DEBUG - Claimed waiting: {v.patient.full_name}, Status: {v.status}, Assigned to: {v.assigned_to}")
    # Latest vaccination records for today per visit
    from django.db.models import OuterRef, Subquery, F
    latest_ts_sq = (VaccinationRecord.objects
                    .filter(visit=OuterRef('visit'))
                    .order_by('-updated_at')
                    .values('updated_at')[:1])
    vacc_records_today = (VaccinationRecord.objects
                          .select_related('visit__patient')
                          .filter(visit__timestamp__date=today)
                          .annotate(latest_updated_at=Subquery(latest_ts_sq))
                          .filter(updated_at=F('latest_updated_at')))
    ready = vacc_records_today.filter(status='queue').order_by('visit__queue_number', 'visit__timestamp')
    in_process = vacc_records_today.filter(status='in_process').order_by('-updated_at')
    not_done = vacc_records_today.filter(status='not_done').order_by('-updated_at')
    completed = vacc_records_today.filter(status='done').order_by('-updated_at')[:20]
    vaccine_type_labels = dict(VaccinationType.choices)
    return render(request, 'dashboard/vaccination.html', {
        'pending_unclaimed': unclaimed,
        'pending_claimed': claimed_waiting,
        'ready': ready,
        'in_process': in_process,
        'not_done': not_done,
        'completed': completed,
        'vaccine_types': VaccinationType.choices,
        'vaccine_type_labels': vaccine_type_labels,
        'today': today,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Vaccination').exists())
@require_POST
def vaccination_claim(request):
    rec_id = request.POST.get('reception_visit_id')
    visit = get_object_or_404(Visit, pk=rec_id, service='reception')
    # Only one claim per ticket; allow re-claim to the same user
    if visit.assigned_to and visit.assigned_to != request.user:
        messages.error(request, 'This ticket is already claimed by another staff.')
        return redirect('dashboard_vaccination')
    visit.assigned_to = request.user
    visit.claimed_at = timezone.now()
    visit.status = Visit.Status.CLAIMED
    visit.save(update_fields=['assigned_to', 'claimed_at', 'status'])
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': 'Claimed', 'patient_id': visit.patient_id})
    messages.success(request, 'Ticket claimed. Verify QR on arrival, then receive to start.')
    return redirect('dashboard_vaccination')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Vaccination').exists())
@require_POST
def vaccination_receive(request):
    rec_id = request.POST.get('reception_visit_id')
    src = get_object_or_404(Visit, pk=rec_id, service='reception')
    with transaction.atomic():
        if not src.assigned_to:
            messages.error(request, 'Please claim this ticket first, then verify QR on arrival.')
            return redirect('dashboard_vaccination')
        verify_code = (request.POST.get('verify_code') or '').strip()
        patient_email = (request.POST.get('patient_email') or '').strip()
        if not verify_code and not patient_email:
            messages.error(request, 'Please verify patient on arrival (scan QR or enter email).')
            return redirect('dashboard_vaccination')
        if patient_email:
            try:
                p = Patient.objects.get(email=patient_email)
            except Patient.DoesNotExist:
                messages.error(request, 'Patient not found for the provided email.')
                return redirect('dashboard_vaccination')
            if src.patient_id != p.id:
                messages.error(request, 'Provided email does not match the expected patient for this ticket.')
                return redirect('dashboard_vaccination')
        elif verify_code:
            if getattr(src.patient, 'patient_code', '').strip().upper() != verify_code.strip().upper():
                messages.error(request, 'QR/Patient code does not match the expected patient for this ticket.')
                return redirect('dashboard_vaccination')
        # Mark arrival on the reception record
        src.status = Visit.Status.IN_PROCESS
        src.save(update_fields=['status'])
        # Create vaccination visit and seed VaccinationRecord in queue or in_process depending on selection
        vtype = (request.POST.get('vaccine_type') or '').strip() or VaccinationType.COVID19
        new_visit = Visit.objects.create(
            patient=src.patient,
            service='vaccination',
            notes=f"Received for vaccination. From reception #{src.id}.",
            queue_number=src.queue_number,
            created_by=request.user,
            assigned_to=request.user,
        )
        vr_status = 'in_process' if vtype else 'queue'
        VaccinationRecord.objects.create(
            visit=new_visit,
            patient=src.patient,
            vaccine_type=vtype,
            status=vr_status,
            details={},
            administered_by=request.user,
        )
        # Move Visit into in-process immediately when a type is set
        if vtype:
            new_visit.status = Visit.Status.IN_PROCESS
            new_visit.save(update_fields=['status'])
        ActivityLog.objects.create(
            actor=request.user,
            verb='Vaccination Receive',
            description=f"Vaccine type: {vtype}",
            patient=src.patient,
        )
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Patient moved to In Process.' if vtype else 'Patient moved to Ready.', 'status': vr_status, 'patient_id': new_visit.patient_id, 'vacc_visit_id': new_visit.id})
    messages.success(request, 'Patient moved to In Process.')
    return redirect('dashboard_vaccination')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Vaccination').exists())
@require_POST
def vaccination_verify_email(request):
    try:
        rec_id = int(request.POST.get('reception_visit_id') or '0')
    except Exception:
        rec_id = 0
    email = (request.POST.get('patient_email') or '').strip()
    if not rec_id or not email:
        return JsonResponse({'success': False, 'message': 'Missing visit or email.'}, status=400)
    visit = Visit.objects.filter(pk=rec_id, service='reception').select_related('patient').first()
    if not visit:
        return JsonResponse({'success': False, 'message': 'Reception visit not found.'}, status=404)
    if not visit.patient or visit.patient.email.strip().lower() != email.strip().lower():
        return JsonResponse({'success': False, 'message': 'Email does not match this patient.'}, status=400)
    return JsonResponse({'success': True})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Vaccination').exists())
def vaccination_work(request, pk: int):
    vacc_visit = get_object_or_404(Visit, pk=pk, service='vaccination')
    vr = VaccinationRecord.objects.filter(visit=vacc_visit).order_by('-updated_at').first()
    if not vr:
        vr = VaccinationRecord.objects.create(visit=vacc_visit, patient=vacc_visit.patient, vaccine_type=VaccinationType.COVID19)
    if request.method == 'POST':
        form = VaccinationForm(request.POST, instance=vr, initial={'vaccine_type': vr.vaccine_type})
        if form.is_valid():
            vr.vaccine_type = form.cleaned_data['vaccine_type']
            vr.details = form.to_details_json()
            action = request.POST.get('action')
            if action == 'done':
                vr.status = 'done'
                vacc_visit.status = Visit.Status.DONE
                vacc_visit.vaccination_date = timezone.localdate()
                vacc_visit.save(update_fields=['status','vaccination_date'])
                # Reflect completion on the specific reception ticket that spawned this vaccination visit
                rec = None
                try:
                    m = re.search(r"From\s+reception\s+#(\d+)", vacc_visit.notes or '', flags=re.IGNORECASE)
                    if m:
                        rec_id = int(m.group(1))
                        rec = Visit.objects.filter(pk=rec_id, service='reception').first()
                except Exception:
                    rec = None
                if not rec:
                    # Fallback: latest today's reception vaccination ticket for this patient
                    rec = (Visit.objects
                           .filter(service='reception', patient=vacc_visit.patient, timestamp__date=timezone.localdate())
                           .filter(Q(service_type__name__iexact='Vaccination') | Q(notes__icontains='[visit: vaccination]'))
                           .order_by('-timestamp')
                           .first())
                if rec:
                    rec.status = Visit.Status.DONE
                    rec.save(update_fields=['status'])
            elif action == 'not_done':
                vr.status = 'not_done'
                vacc_visit.status = Visit.Status.IN_PROCESS
                vacc_visit.save(update_fields=['status'])
            else:
                vr.status = 'in_process'
                vacc_visit.status = Visit.Status.IN_PROCESS
                vacc_visit.save(update_fields=['status'])
            vr.administered_by = request.user
            vr.save()
            messages.success(request, 'Vaccination record saved.')
            return redirect('dashboard_vaccination')
    else:
        form = VaccinationForm(instance=vr, initial={'vaccine_type': vr.vaccine_type})
    return render(request, 'dashboard/vaccination_work.html', {'visit': vacc_visit, 'form': form, 'vacc_record': vr})


@login_required
def reports(request):
    # Filters
    start = request.GET.get('start')
    end = request.GET.get('end')
    service = request.GET.get('service')
    qs = Visit.objects.select_related('patient').order_by('-timestamp')
    if start:
        qs = qs.filter(timestamp__date__gte=start)
    if end:
        qs = qs.filter(timestamp__date__lte=end)
    if service:
        qs = qs.filter(service=service)
    # Enforce per-doctor scoping for non-admin doctors
    try:
        is_doctor = request.user.is_authenticated and request.user.groups.filter(name='Doctor').exists()
    except Exception:
        is_doctor = False
    if is_doctor and not request.user.is_superuser:
        qs = qs.filter(service='doctor', doctor_user=request.user)
    export = request.GET.get('export')
    if export == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="visits.csv"'
        writer = csv.writer(resp)
        writer.writerow(['Date','Service','Patient','Notes'])
        for v in qs:
            writer.writerow([v.timestamp.strftime('%Y-%m-%d %H:%M'), v.get_service_display(), v.patient.full_name, v.notes])
        return resp
    if export == 'xlsx':
        if not Workbook:
            messages.error(request, 'XLSX export is unavailable (openpyxl not installed).')
            return redirect('dashboard_reports')
        wb = Workbook()
        ws = wb.active
        ws.title = 'Visits'
        ws.append(['Date','Service','Patient','Notes'])
        for v in qs:
            ws.append([v.timestamp.strftime('%Y-%m-%d %H:%M'), v.get_service_display(), v.patient.full_name, v.notes])
        resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = 'attachment; filename="visits.xlsx"'
        wb.save(resp)
        return resp
    if export == 'pdf':
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
        except Exception:
            messages.error(request, 'PDF export is unavailable (reportlab not installed).')
            return redirect('dashboard_reports')
        resp = HttpResponse(content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="visits.pdf"'
        p = canvas.Canvas(resp, pagesize=A4)
        width, height = A4
        y = height - 40
        p.setFont("Helvetica-Bold", 12)
        p.drawString(40, y, "Clinic Visits Report")
        y -= 20
        p.setFont("Helvetica", 9)
        p.drawString(40, y, f"Filters: start={start or '-'} end={end or '-'} service={service or '-'}")
        y -= 20
        p.setFont("Helvetica-Bold", 10)
        p.drawString(40, y, "Date")
        p.drawString(150, y, "Service")
        p.drawString(230, y, "Patient")
        p.drawString(380, y, "Notes")
        y -= 14
        p.setFont("Helvetica", 9)
        for v in qs[:500]:
            if y < 40:
                p.showPage()
                y = height - 40
            p.drawString(40, y, v.timestamp.strftime('%Y-%m-%d %H:%M'))
            p.drawString(150, y, v.get_service_display())
            p.drawString(230, y, v.patient.full_name[:22])
            p.drawString(380, y, (v.notes or '')[:40])
            y -= 12
        p.showPage()
        p.save()
        return resp
    return render(request, 'dashboard/reports.html', {'visits': qs, 'start': start or '', 'end': end or '', 'service': service or ''})


@login_required
def api_patient_by_code(request, code: str):
    # Minimal JSON for pharmacy/doctor UIs
    p = Patient.objects.filter(patient_code=code).first()
    if not p:
        return JsonResponse({'error': 'not_found'}, status=404)
    # Find latest doctor prescription notes
    last_rx = (Visit.objects
               .filter(patient=p, service='doctor')
               .exclude(prescription_notes='')
               .order_by('-timestamp')
               .values_list('prescription_notes', flat=True)
               .first()) or ''
    return JsonResponse({
        'id': p.id,
        'full_name': p.full_name,
        'age': p.age,
        'patient_code': p.patient_code,
        'allergies': getattr(p, 'allergies', ''),
        'last_prescription': last_rx,
    })

@login_required
@user_passes_test(is_admin)
def doctor_list(request):
    doctors = Doctor.objects.select_related('user').order_by('full_name')
    return render(request, 'dashboard/doctors/list.html', {'doctors': doctors})


@login_required
@user_passes_test(is_admin)
def doctor_create(request):
    if request.method == 'POST':
        form = DoctorForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['email'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'] or User.objects.make_random_password(),
            )
            # Add to Doctor group
            group, _ = Group.objects.get_or_create(name='Doctor')
            user.groups.add(group)
            doctor = Doctor.objects.create(
                user=user,
                full_name=form.cleaned_data['full_name'],
                specialization=form.cleaned_data['specialization'],
            )
            return redirect('doctor_list')
    else:
        form = DoctorForm()
    return render(request, 'dashboard/doctors/form.html', {'form': form, 'is_edit': False})


@login_required
@user_passes_test(is_admin)
def doctor_edit(request, pk: int):
    doctor = get_object_or_404(Doctor, pk=pk)
    if request.method == 'POST':
        form = DoctorForm(request.POST, instance=doctor)
        if form.is_valid():
            doctor.full_name = form.cleaned_data['full_name']
            doctor.specialization = form.cleaned_data['specialization']
            doctor.save()
            # Update email and password if provided
            doctor.user.email = form.cleaned_data['email']
            doctor.user.username = form.cleaned_data['email']
            if form.cleaned_data['password']:
                doctor.user.set_password(form.cleaned_data['password'])
            doctor.user.save()
            return redirect('doctor_list')
    else:
        form = DoctorForm(instance=doctor)
    return render(request, 'dashboard/doctors/form.html', {'form': form, 'is_edit': True, 'doctor': doctor})


@login_required
@user_passes_test(is_admin)
def doctor_delete(request, pk: int):
    doctor = get_object_or_404(Doctor, pk=pk)
    if request.method == 'POST':
        user = doctor.user
        doctor.delete()
        user.delete()
        return redirect('doctor_list')
    return render(request, 'dashboard/doctors/delete_confirm.html', {'doctor': doctor})


@login_required
def doctor_claim(request):
    if request.method != 'POST' or not request.user.groups.filter(name='Doctor').exists():
        return redirect('dashboard_doctor')
    today = timezone.localdate()
    rid = request.POST.get('reception_visit_id')
    visit = get_object_or_404(Visit, pk=rid, service='reception', claimed_by__isnull=True)
    # Enforce department match between doctor specialization and queued department
    try:
        doctor_dept = request.user.doctor_profile.specialization
    except Doctor.DoesNotExist:
        doctor_dept = None
    if not doctor_dept or (visit.department and visit.department != doctor_dept):
        messages.error(request, 'You can only claim patients queued for your department.')
        return redirect('dashboard_doctor')
    with transaction.atomic():
        # store department and current queue number for renumbering
        dept = visit.department
        claimed_q = visit.queue_number or 0
        visit.claimed_by = request.user
        visit.claimed_at = timezone.now()
        visit.queue_number = None
        visit.status = Visit.Status.CLAIMED
        visit.save(update_fields=['claimed_by', 'claimed_at', 'queue_number', 'status'])
        # Renumber: shift down others in same department and day with higher queue numbers
        if claimed_q:
            others = (Visit.objects
                      .filter(service='reception', timestamp__date=today, department=dept, claimed_by__isnull=True, queue_number__gt=claimed_q)
                      .order_by('queue_number'))
            for v in others:
                v.queue_number = (v.queue_number or 1) - 1
                v.save(update_fields=['queue_number'])
    messages.success(request, 'Patient claimed.')
    return redirect('dashboard_doctor')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Doctor').exists())
@require_POST
def doctor_verify_arrival(request):
    rid = request.POST.get('reception_visit_id')
    print(f"Doctor verify arrival - Visit ID: {rid}, User: {request.user}")
    
    visit = get_object_or_404(Visit, pk=rid, service='reception', claimed_by=request.user)
    
    # Support both email-based QR scanning and manual code verification
    patient_email = request.POST.get('patient_email', '').strip()
    verify_code = request.POST.get('verify_code', '').strip()
    
    print(f"Patient email: {patient_email}, Verify code: {verify_code}")
    
    if not patient_email and not verify_code:
        messages.error(request, 'Please verify patient QR on arrival.')
        return redirect('dashboard_doctor')
    
    # Validate patient if email is provided (QR scan)
    if patient_email:
        try:
            patient = Patient.objects.get(email=patient_email)
            if visit.patient != patient:
                error_msg = 'Invalid patient QR. Please scan a registered patient.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                messages.error(request, error_msg)
                return redirect('dashboard_doctor')
        except Patient.DoesNotExist:
            error_msg = 'Invalid patient QR. Please scan a registered patient.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            messages.error(request, error_msg)
            return redirect('dashboard_doctor')
    else:
        # Manual code verification
        if visit.patient.patient_code.strip().upper() != verify_code.strip().upper():
            error_msg = 'QR/Patient code does not match.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            messages.error(request, error_msg)
            return redirect('dashboard_doctor')
    
    # Update status
    visit.doctor_arrived = True
    visit.doctor_status = 'ready_to_consult'
    # Reflect unified status as claimed (ready to consult)
    visit.status = Visit.Status.CLAIMED
    visit.save(update_fields=['doctor_arrived', 'doctor_status', 'status'])
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        print(f"AJAX request - returning success for visit {visit.id}, patient {visit.patient.full_name}")
        return JsonResponse({
            'success': True,
            'message': 'Patient verified! Status updated to Ready to Consult.',
            'patient_name': visit.patient.full_name,
            'visit_id': visit.id
        })
    
    messages.success(request, 'Patient verified! Status updated to Ready to Consult.')
    return redirect('dashboard_doctor')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Doctor').exists())
def doctor_consult(request, rid: int):
    # rid points to the reception Visit that was claimed
    rec = get_object_or_404(Visit, pk=rid, service='reception', claimed_by=request.user)
    if not rec.doctor_arrived:
        messages.error(request, 'Please verify patient arrival first.')
        return redirect('dashboard_doctor')
    if request.method == 'POST':
        symptoms = request.POST.get('symptoms','')
        diagnosis = request.POST.get('diagnosis','')
        prescription_notes = request.POST.get('prescription_notes','')
        mark = request.POST.get('status')
        done = (mark == 'done')
        with transaction.atomic():
            # Upsert today's draft for this doctor and patient
            draft = (Visit.objects
                     .filter(service='doctor', doctor_user=request.user, doctor_done=False, patient=rec.patient, timestamp__date=timezone.localdate())
                     .order_by('-timestamp')
                     .first())
            if draft:
                draft.symptoms = symptoms
                draft.diagnosis = diagnosis
                draft.prescription_notes = prescription_notes
                if done:
                    draft.doctor_done = True
                    draft.doctor_done_at = timezone.now()
                    draft.status = Visit.Status.DONE
                else:
                    draft.status = Visit.Status.IN_PROCESS
                draft.save()
            else:
                draft = Visit.objects.create(
                    patient=rec.patient,
                    service='doctor',
                    symptoms=symptoms,
                    diagnosis=diagnosis,
                    prescription_notes=prescription_notes,
                    doctor_user=request.user,
                    doctor_done=done,
                    doctor_done_at=timezone.now() if done else None,
                    status=Visit.Status.DONE if done else Visit.Status.IN_PROCESS,
                    created_by=request.user,
                )
        # Update the reception ticket status according to action
        rec.doctor_status = 'finished' if done else 'in_consultation'
        # Also reflect unified status on the reception ticket
        rec.status = Visit.Status.DONE if done else Visit.Status.IN_PROCESS
        rec.save(update_fields=['doctor_status', 'status'])
        messages.success(request, 'Consultation {}.'.format('completed' if done else 'saved as not done'))
        return redirect('dashboard_doctor')
    # If there is an existing not-done consultation for this patient today, load to edit
    draft = (Visit.objects
             .filter(service='doctor', doctor_user=request.user, doctor_done=False, patient=rec.patient, timestamp__date=timezone.localdate())
             .order_by('-timestamp')
             .first())
    return render(request, 'dashboard/doctor_consult.html', {'rec': rec, 'draft': draft})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Doctor').exists())
@require_POST
def doctor_finish_inprogress(request, rid: int):
    # Finish an in-progress doctor visit (draft) by id
    v = get_object_or_404(Visit, pk=rid, service='doctor', doctor_user=request.user, doctor_done=False)
    v.doctor_done = True
    v.doctor_done_at = timezone.now()
    v.status = Visit.Status.DONE
    v.save(update_fields=['doctor_done', 'doctor_done_at', 'status'])
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': 'Finished', 'patient_id': v.patient_id})
    messages.success(request, 'Consultation marked as done.')
    # Reflect status on reception ticket
    today = timezone.localdate()
    rec = (Visit.objects
           .filter(service='reception', claimed_by=request.user, patient=v.patient, timestamp__date=today)
           .order_by('-timestamp')
           .first())
    if rec:
        rec.doctor_status = 'finished'
        rec.status = Visit.Status.DONE
        rec.save(update_fields=['doctor_status', 'status'])
    return redirect('dashboard_doctor')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Doctor').exists())
def doctor_consult_edit(request, did: int):
    # Edit an in-progress (not done) doctor visit
    visit = get_object_or_404(Visit, pk=did, service='doctor', doctor_user=request.user, doctor_done=False)
    if request.method == 'POST':
        visit.symptoms = request.POST.get('symptoms','')
        visit.diagnosis = request.POST.get('diagnosis','')
        visit.prescription_notes = request.POST.get('prescription_notes','')
        mark = request.POST.get('status')
        done = (mark == 'done')
        if done:
            visit.doctor_done = True
            visit.doctor_done_at = timezone.now()
        visit.save()
        # Reflect status on reception ticket
        today = timezone.localdate()
        rec = (Visit.objects
               .filter(service='reception', claimed_by=request.user, patient=visit.patient, timestamp__date=today)
               .order_by('-timestamp')
               .first())
        if rec:
            rec.doctor_status = 'finished' if done else 'in_consultation'
            rec.save(update_fields=['doctor_status'])
        messages.success(request, 'Consultation {}.'.format('completed' if done else 'updated'))
        return redirect('dashboard_doctor')
    # Reuse consult template
    return render(request, 'dashboard/doctor_consult.html', {'rec': None, 'draft': visit, 'is_edit': True})
