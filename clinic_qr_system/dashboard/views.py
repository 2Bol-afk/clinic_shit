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
        _ = request.user.patient_profile
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
    return render(request, 'dashboard/reception.html', {'visits': visits, 'today': today})


@login_required
@user_passes_test(is_reception)
def reception_edit(request, pk: int):
    visit = get_object_or_404(Visit, pk=pk, service='reception')
    if request.method == 'POST':
        visit.department = request.POST.get('department') or visit.department
        qn = request.POST.get('queue_number')
        visit.queue_number = int(qn) if qn else visit.queue_number
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
    recent = (Visit.objects
              .filter(service='doctor', timestamp__date=today)
              .select_related('patient', 'created_by')
              .order_by('-timestamp'))
    # Timeline for this doctor if user is a doctor
    timeline = Visit.objects.none()
    waiting = Visit.objects.none()
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
        timeline = Visit.objects.filter(doctor_user=request.user).select_related('patient').order_by('-timestamp')[:50]
    return render(request, 'dashboard/doctor.html', {'visits': recent, 'today': today, 'timeline': timeline, 'waiting': waiting, 'unfinished': unfinished})


@login_required
def lab_dashboard(request):
    # Show pending lab requests
    pending = (Visit.objects
               .filter(service='doctor')
               .exclude(lab_tests='')
               .order_by('-timestamp'))
    completed = (Visit.objects
                 .filter(service='lab')
                 .order_by('-timestamp')[:50])
    return render(request, 'dashboard/lab.html', {'pending': pending, 'completed': completed})


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
    # Prevent claim if unfinished doctor consultation exists today
    if Visit.objects.filter(service='doctor', doctor_user=request.user, doctor_done=False, timestamp__date=today).exists():
        messages.error(request, 'Finish your current consultation before claiming another patient.')
        return redirect('dashboard_doctor')
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
        # Redirect doctor to scan with prefilled patient code
        code = visit.patient.patient_code
    messages.success(request, 'Patient claimed. Scan the QR to log consultation.')
    return redirect(f'/visits/scan/?code={code}')
