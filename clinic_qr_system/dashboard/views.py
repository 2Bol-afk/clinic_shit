from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db import models, transaction
from patients.models import Patient, Doctor
from visits.models import Visit
from django.contrib.auth.models import Group, User
from .models import ActivityLog
from patients.forms import DoctorForm
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.http import JsonResponse
import csv
try:
    from openpyxl import Workbook
except Exception:
    Workbook = None


def is_admin(user):
    return user.is_superuser


def is_reception(user):
    return user.is_superuser or user.groups.filter(name='Reception').exists()


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
    except Exception:
        return redirect('dashboard_index')


@login_required
def reception_dashboard(request):
    today = timezone.localdate()
    visits = (Visit.objects
              .filter(service='reception', timestamp__date=today)
              .select_related('patient', 'created_by')
              .order_by('-timestamp'))
    # Patients with completed doctor consultations today
    completed_doctor_patients = set(
        Visit.objects
        .filter(service='doctor', doctor_done=True, timestamp__date=today)
        .values_list('patient_id', flat=True)
    )
    return render(
        request,
        'dashboard/reception.html',
        {
            'visits': visits,
            'today': today,
            'completed_doctor_patients': completed_doctor_patients,
        },
    )


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
    # Only exclude patients already in an in-progress lab visit today
    already_in_lab = (Visit.objects
                      .filter(service='lab', lab_completed=False, timestamp__date=today)
                      .values_list('patient_id', flat=True))
    pending = (Visit.objects
               .filter(service='reception', timestamp__date=today)
               .filter(notes__icontains='[visit: laboratory]')
               .exclude(patient_id__in=already_in_lab)
               .order_by('queue_number', 'timestamp'))
    # Split into unclaimed vs claimed (still waiting to arrive)
    unclaimed = pending.filter(lab_claimed_by__isnull=True)
    claimed_waiting = pending.filter(lab_claimed_by__isnull=False, lab_arrived=False)
    # In-progress and completed for lab
    in_progress = (Visit.objects
                   .filter(service='lab', lab_completed=False)
                   .order_by('-timestamp'))
    completed = (Visit.objects
                 .filter(service='lab', lab_completed=True)
                 .order_by('-lab_completed_at', '-timestamp')[:5])
    return render(request, 'dashboard/lab.html', {
        'pending_unclaimed': unclaimed,
        'pending_claimed': claimed_waiting,
        'in_progress': in_progress,
        'completed': completed,
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
    visit.save(update_fields=['lab_claimed_by', 'lab_claimed_at'])
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
        # If coming from reception, optionally verify QR code matches patient
        if rec_id:
            verify_code = (request.POST.get('verify_code') or '').strip()
            if not verify_code:
                messages.error(request, 'Please verify patient QR on arrival before receiving.')
                return redirect('dashboard_lab')
            if getattr(src.patient, 'patient_code', '').strip().upper() != verify_code.strip().upper():
                messages.error(request, 'QR/Patient code does not match the expected patient for this ticket.')
                return redirect('dashboard_lab')
            # Mark arrival on the reception record
            if not src.lab_arrived:
                src.lab_arrived = True
                src.save(update_fields=['lab_arrived'])
        # Carry over queue number for reception-tagged lab arrivals
        qn = src.queue_number if (src_type == 'reception' and src.queue_number) else None
        test_type = request.POST.get('lab_test_type', '').strip()
        Visit.objects.create(
            patient=src.patient,
            service='lab',
            notes=(f"Received for lab. From {src_type} #{src.id}."),
            lab_tests=(src.lab_tests if hasattr(src, 'lab_tests') else '') or (src.prescription_notes if hasattr(src, 'prescription_notes') else ''),
            lab_test_type=test_type,
            queue_number=qn,
            created_by=request.user,
        )
        ActivityLog.objects.create(
            actor=request.user,
            verb='Lab Receive',
            description=f"Received tests: {(src.lab_tests if hasattr(src, 'lab_tests') else '') or (src.prescription_notes if hasattr(src, 'prescription_notes') else '')}",
            patient=src.patient,
        )
    messages.success(request, 'Patient received in laboratory.')
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
        lab_visit.save(update_fields=['lab_results', 'lab_completed', 'lab_completed_at', 'notes'])
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
        if request.POST.get('complete') == '1':
            lab_visit.lab_completed = True
            lab_visit.lab_completed_at = timezone.now()
        lab_visit.save()
        messages.success(request, 'Lab work saved.')
        if request.POST.get('complete') == '1':
            return redirect('dashboard_lab')
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
    today = timezone.localdate()
    vaccinations = (Visit.objects
                    .filter(service='vaccination', timestamp__date=today)
                    .order_by('-timestamp'))
    return render(request, 'dashboard/vaccination.html', {'vaccinations': vaccinations, 'today': today})


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
    with transaction.atomic():
        # store department and current queue number for renumbering
        dept = visit.department
        claimed_q = visit.queue_number or 0
        visit.claimed_by = request.user
        visit.claimed_at = timezone.now()
        visit.queue_number = None
        visit.save(update_fields=['claimed_by', 'claimed_at', 'queue_number'])
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
    visit = get_object_or_404(Visit, pk=rid, service='reception', claimed_by=request.user)
    verify_code = (request.POST.get('verify_code') or '').strip()
    if not verify_code:
        messages.error(request, 'Please verify patient QR on arrival.')
        return redirect('dashboard_doctor')
    if visit.patient.patient_code.strip().upper() != verify_code.strip().upper():
        messages.error(request, 'QR/Patient code does not match.')
        return redirect('dashboard_doctor')
    visit.doctor_arrived = True
    # Set explicit status for dashboard state machine
    visit.doctor_status = 'ready_to_consult'
    visit.save(update_fields=['doctor_arrived', 'doctor_status'])
    messages.success(request, 'Arrival verified. You can start consultation.')
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
                    created_by=request.user,
                )
        # Update the reception ticket status according to action
        rec.doctor_status = 'finished' if done else 'not_done'
        rec.save(update_fields=['doctor_status'])
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
    v.save(update_fields=['doctor_done', 'doctor_done_at'])
    messages.success(request, 'Consultation marked as done.')
    # Reflect status on reception ticket
    today = timezone.localdate()
    rec = (Visit.objects
           .filter(service='reception', claimed_by=request.user, patient=v.patient, timestamp__date=today)
           .order_by('-timestamp')
           .first())
    if rec:
        rec.doctor_status = 'finished'
        rec.save(update_fields=['doctor_status'])
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
        messages.success(request, 'Consultation {}.'.format('completed' if done else 'updated'))
        return redirect('dashboard_doctor')
    # Reuse consult template
    return render(request, 'dashboard/doctor_consult.html', {'rec': None, 'draft': visit, 'is_edit': True})
