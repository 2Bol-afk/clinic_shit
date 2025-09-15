from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.mail import EmailMessage
from django.conf import settings
from django.db import transaction
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
import uuid
import csv
import pandas as pd
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth import login as auth_login, authenticate

from .forms import PatientRegistrationForm, PatientSignupForm
from .models import Patient


def _generate_patient_code() -> str:
    return uuid.uuid4().hex[:10].upper()


def signup(request):
    if request.method == 'POST':
        form = PatientSignupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                patient: Patient = form.save(commit=False)
                patient.patient_code = _generate_patient_code()
                # Generate QR
                qr_img = qrcode.make(patient.patient_code)
                buffer = BytesIO()
                qr_img.save(buffer, format='PNG')
                file_name = f"qr_{patient.patient_code}.png"
                patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                patient.save()
                # Create user with provided password
                username = f"p_{patient.patient_code.lower()}"
                password = form.cleaned_data['password']
                user = User.objects.create_user(username=username, email=patient.email, password=password)
                patient.user = user
                patient.save(update_fields=['user'])
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)
            # Email QR and confirmation
            email = EmailMessage(
                subject='Your Digital Health Pass',
                body=(
                    f"Dear {patient.full_name},\n\nYour patient code is {patient.patient_code}. "
                    f"Use username {username} to log in."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[patient.email],
            )
            email.attach(file_name, buffer.getvalue(), 'image/png')
            email.send(fail_silently=True)
            # Auto-login
            user = authenticate(request, username=username, password=password)
            if user:
                auth_login(request, user)
                return redirect('patient_portal')
    else:
        form = PatientSignupForm()
    return render(request, 'registration/login.html', {'signup_form': form})


def register(request):
    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                patient: Patient = form.save(commit=False)
                patient.patient_code = _generate_patient_code()

                # Generate QR image with patient_code
                qr_img = qrcode.make(patient.patient_code)
                buffer = BytesIO()
                qr_img.save(buffer, format='PNG')
                file_name = f"qr_{patient.patient_code}.png"
                patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                patient.save()

                # Create user credentials for patient portal
                username = f"p_{patient.patient_code.lower()}"
                temp_password = uuid.uuid4().hex[:12]
                user = User.objects.create_user(username=username, email=patient.email, password=temp_password)
                patient.user = user
                patient.save(update_fields=['user'])
                # Ensure Patient group exists and add user
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)

            # Email QR code + credentials
            if patient.email:
                email = EmailMessage(
                    subject='Your Digital Health Pass & Portal Access',
                    body=(
                        f"Dear {patient.full_name},\n\n"
                        f"Your patient code: {patient.patient_code}.\n"
                        f"Portal login: {username}\n"
                        f"Temporary password: {temp_password}\n\n"
                        f"Please change your password after logging in at /accounts/login/.\n"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[patient.email],
                )
                if patient.qr_code:
                    email.attach(file_name, buffer.getvalue(), 'image/png')
                email.send(fail_silently=True)

            return redirect(reverse('patient_register_success'))
    else:
        form = PatientRegistrationForm()
    return render(request, 'patients/register.html', {'form': form})


def register_success(request):
    return render(request, 'patients/register_success.html')


@login_required
def patient_list(request):
    qs = Patient.objects.order_by('-created_at')
    return render(request, 'patients/patient_list.html', {'patients': qs})


@login_required
def patient_detail(request, pk: int):
    patient = get_object_or_404(Patient, pk=pk)
    visits = patient.visits.order_by('-timestamp')
    return render(request, 'patients/patient_detail.html', {'patient': patient, 'visits': visits})


@login_required
def report_daily_csv(request):
    from django.utils import timezone
    from visits.models import Visit
    today = timezone.localdate()
    visits = Visit.objects.filter(timestamp__date=today).select_related('patient', 'created_by')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="daily_{today}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Patient', 'Code', 'Service', 'Notes', 'Timestamp', 'Staff'])
    for v in visits:
        writer.writerow([
            v.patient.full_name,
            v.patient.patient_code,
            v.get_service_display(),
            v.notes,
            v.timestamp.isoformat(),
            v.created_by.username if v.created_by else '',
        ])
    return response


@login_required
def report_daily_xlsx(request):
    from django.utils import timezone
    from visits.models import Visit
    today = timezone.localdate()
    visits = Visit.objects.filter(timestamp__date=today).select_related('patient', 'created_by')
    data = [
        {
            'Patient': v.patient.full_name,
            'Code': v.patient.patient_code,
            'Service': v.get_service_display(),
            'Notes': v.notes,
            'Timestamp': v.timestamp,
            'Staff': v.created_by.username if v.created_by else '',
        }
        for v in visits
    ]
    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="daily_{today}.xlsx"'
    with BytesIO() as b:
        df.to_excel(b, index=False)
        response.write(b.getvalue())
    return response


@login_required
def portal_home(request):
    # Only for users linked to a Patient profile
    try:
        patient = request.user.patient_profile
    except Patient.DoesNotExist:
        return render(request, 'patients/portal_not_linked.html')
    visits = patient.visits.order_by('-timestamp')
    # Extract latest doctor prescription and pharmacy dispenses
    latest_doctor = visits.filter(service='doctor').first()
    latest_pharmacy = visits.filter(service='pharmacy').first()
    context = {
        'patient': patient,
        'visits': visits,
        'latest_doctor': latest_doctor,
        'latest_pharmacy': latest_pharmacy,
    }
    return render(request, 'patients/portal_home.html', context)
