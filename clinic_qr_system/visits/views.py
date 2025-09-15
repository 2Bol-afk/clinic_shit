from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from patients.models import Patient
from .models import Visit
from django.contrib.auth.models import Group
from dashboard.models import ActivityLog
from django.contrib import messages


@login_required
def scan(request):
    context = {}
    # Prefill code from query param
    if request.method == 'GET':
        code = request.GET.get('code')
        if code:
            context['prefill_code'] = code
    # Expose role flags to the template safely
    try:
        context['is_doctor'] = request.user.groups.filter(name='Doctor').exists()
    except Exception:
        context['is_doctor'] = False
    try:
        context['is_reception'] = request.user.groups.filter(name='Reception').exists()
    except Exception:
        context['is_reception'] = False
    if request.method == 'POST':
        code = request.POST.get('patient_code', '').strip()
        service = request.POST.get('service', '').strip()
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
                if service == 'reception':
                    # Department and queue assignment
                    dept = request.POST.get('department')
                    if dept:
                        kwargs['department'] = dept
                    qn = request.POST.get('queue_number')
                    if qn:
                        kwargs['queue_number'] = int(qn)
                    else:
                        # auto-assign next queue number for today and department
                        today = timezone.localdate()
                        last = (Visit.objects
                                .filter(service='reception', timestamp__date=today, department=dept)
                                .order_by('-queue_number')
                                .first())
                        next_q = (last.queue_number + 1) if last and last.queue_number else 1
                        kwargs['queue_number'] = next_q
                elif service == 'doctor':
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
    return render(request, 'visits/scan.html', context)

# Create your views here.
