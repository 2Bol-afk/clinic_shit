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
from django.http import HttpResponse, JsonResponse
import threading
from django.contrib import messages
import os
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.contrib.auth import login as auth_login, authenticate
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordChangeView
from django.http import HttpResponseForbidden

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
                # Generate QR containing Gmail + Patient ID (ID is available after first save below)
                file_name = f"qr_{patient.patient_code}.png"
                patient.save()  # Save first to get patient ID
                
                # Generate QR with email and patient ID
                buffer = None
                try:
                    qr_payload = f"email:{patient.email};id:{patient.id}"
                    qr_img = qrcode.make(qr_payload)
                    buffer = BytesIO()
                    qr_img.save(buffer, format='PNG')
                    patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                    patient.save(update_fields=['qr_code'])
                except Exception:
                    pass
                # Create user with provided password
                username = f"p_{patient.patient_code.lower()}"
                password = form.cleaned_data['password']
                user = User.objects.create_user(username=username, email=patient.email, password=password)
                patient.user = user
                patient.save(update_fields=['user'])
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)
            # Email QR and confirmation (synchronous send for clear feedback)
            try:
                if patient.email:
                    body = (
                        f"Dear {patient.full_name},\n\nYour patient code is {patient.patient_code}. "
                        f"Use username {username} to log in."
                    )
                    msg = EmailMessage(
                        subject='Your Digital Health Pass',
                        body=body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[patient.email],
                    )
                    qr_path = getattr(patient.qr_code, 'path', None)
                    if qr_path:
                        try:
                            with open(qr_path, 'rb') as f:
                                msg.attach(file_name, f.read(), 'image/png')
                        except Exception:
                            pass
                    elif buffer:
                        msg.attach(file_name, buffer.getvalue(), 'image/png')
                    sent = msg.send(fail_silently=False)
                    if sent:
                        messages.success(request, f'Confirmation email sent to {patient.email}.')
                    else:
                        messages.warning(request, f'Confirmation email not sent to {patient.email}.')
            except Exception as e:
                messages.error(request, f'Email send failed: {e}')
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

                # Generate QR containing Gmail + Patient ID (ID will exist after first save)
                file_name = f"qr_{patient.patient_code}.png"
                patient.save()  # Save first to get patient ID
                
                # Generate QR with email and patient ID
                buffer = None
                try:
                    qr_payload = f"email:{patient.email};id:{patient.id}"
                    qr_img = qrcode.make(qr_payload)
                    buffer = BytesIO()
                    qr_img.save(buffer, format='PNG')
                    patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
                    patient.save(update_fields=['qr_code'])
                except Exception:
                    pass

                # Create user credentials for patient portal
                username = f"p_{patient.patient_code.lower()}"
                temp_password = uuid.uuid4().hex[:12]
                user = User.objects.create_user(username=username, email=patient.email, password=temp_password)
                patient.user = user
                patient.must_change_password = True
                patient.save(update_fields=['user','must_change_password'])
                # Ensure Patient group exists and add user
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)

            # Email QR code + credentials (synchronous send for clear feedback)
            try:
                if patient.email:
                    body = (
                        f"Dear {patient.full_name},\n\n"
                        f"Your patient code: {patient.patient_code}.\n"
                        f"Portal login: {username}\n"
                        f"Temporary password: {temp_password}\n\n"
                        f"Please change your password after logging in at /accounts/login/.\n"
                    )
                    msg = EmailMessage(
                        subject='Your Digital Health Pass & Portal Access',
                        body=body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[patient.email],
                    )
                    qr_path = getattr(patient.qr_code, 'path', None)
                    if qr_path:
                        try:
                            with open(qr_path, 'rb') as f:
                                msg.attach(file_name, f.read(), 'image/png')
                        except Exception:
                            pass
                    elif buffer:
                        msg.attach(file_name, buffer.getvalue(), 'image/png')
                    sent = msg.send(fail_silently=False)
                    if sent:
                        messages.success(request, f'Confirmation email sent to {patient.email}.')
                    else:
                        messages.warning(request, f'Confirmation email not sent to {patient.email}.')
            except Exception as e:
                messages.error(request, f'Email send failed: {e}')

            messages.success(request, 'Registration complete.')
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
    visits = patient.visits.select_related('created_by').order_by('-timestamp')
    doctor_visits = visits.filter(service='doctor')
    pharmacy_visits = visits.filter(service='pharmacy')
    lab_visits = visits.filter(service='lab').order_by('-timestamp')[:10]
    latest_doctor = doctor_visits.first()
    latest_pharmacy = pharmacy_visits.first()
    active_prescriptions = list(doctor_visits.exclude(prescription_notes='')[:5])
    # Dispense state heuristic: if there is a recent pharmacy visit after latest doctor
    dispensed_recent = latest_pharmacy if latest_pharmacy else None
    context = {
        'patient': patient,
        'visits': visits,
        'doctor_visits': doctor_visits[:10],
        'lab_visits': lab_visits,
        'active_prescriptions': active_prescriptions,
        'latest_doctor': latest_doctor,
        'latest_pharmacy': latest_pharmacy,
        'dispensed_recent': dispensed_recent,
    }
    return render(request, 'patients/patient_detail.html', context)


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


class PatientPasswordChangeView(PasswordChangeView):
    success_url = reverse_lazy('patient_portal')

    def form_valid(self, form):
        response = super().form_valid(form)
        try:
            p = self.request.user.patient_profile
            if p.must_change_password:
                p.must_change_password = False
                p.save(update_fields=['must_change_password'])
        except Patient.DoesNotExist:
            pass
        return response


@login_required
def password_first_change(request):
    # Only patients, and only when flagged
    try:
        patient = request.user.patient_profile
    except Patient.DoesNotExist:
        return HttpResponseForbidden('Only patients can change password here.')
    if not patient.must_change_password:
        return redirect('patient_portal')
    ctx = {
        'email': request.user.email,
    }
    if request.method == 'POST':
        pwd = request.POST.get('password') or ''
        pwd2 = request.POST.get('password_confirm') or ''
        if len(pwd) < 8:
            ctx['error'] = 'Password must be at least 8 characters.'
            return render(request, 'patients/password_first_change.html', ctx)
        if pwd != pwd2:
            ctx['error'] = 'Passwords do not match.'
            return render(request, 'patients/password_first_change.html', ctx)
        # Set new password and keep user logged in
        user = request.user
        user.set_password(pwd)
        user.save()
        patient.must_change_password = False
        patient.save(update_fields=['must_change_password'])
        # Re-authenticate using email backend; email or username supported
        user = authenticate(request, username=user.email or user.username, password=pwd)
        if user:
            auth_login(request, user)
        return redirect('patient_portal')
    return render(request, 'patients/password_first_change.html', ctx)


def qr_login(request):
    """QR-based patient login page"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            return render(request, 'patients/qr_login.html', {'error': 'Please enter your email address.'})
        
        try:
            patient = Patient.objects.get(email=email)
            if patient.user:
                # Auto-login the patient with the correct backend
                from clinic_qr_system.backends import EmailOrUsernameModelBackend
                auth_login(request, patient.user, backend='clinic_qr_system.backends.EmailOrUsernameModelBackend')
                return redirect('patient_portal')
            else:
                return render(request, 'patients/qr_login.html', {'error': 'Patient account not properly linked. Please contact support.'})
        except Patient.DoesNotExist:
            return render(request, 'patients/qr_login.html', {'error': 'No patient found with this email address. Please register first.'})
    
    return render(request, 'patients/qr_login.html')


def qr_scan_api(request):
    """API endpoint for QR code scanning - returns patient data by email.
    Accepts POST (form) or GET (?email=...)
    """
    if request.method not in ['POST', 'GET']:
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    email = (request.POST.get('email') if request.method == 'POST' else request.GET.get('email')) or ''
    email = email.strip()
    if not email:
        return JsonResponse({'error': 'Email required'}, status=400)

    # Validate email format
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return JsonResponse({
            'error': 'Invalid email format. Please scan a valid QR code or use a registered email address.',
            'error_type': 'invalid_format'
        }, status=400)

    try:
        patient = Patient.objects.get(email=email)
        visits_qs = patient.visits.order_by('-timestamp')
        visits = list(visits_qs[:10])
        latest_doctor = visits_qs.filter(service='doctor').first()
        latest_pharmacy = visits_qs.filter(service='pharmacy').first()

        return JsonResponse({
            'success': True,
            'patient': {
                'id': patient.id,
                'full_name': patient.full_name,
                'age': patient.age,
                'email': patient.email,
                'patient_code': patient.patient_code,
                'qr_code_url': patient.qr_code.url if patient.qr_code else None,
            },
            'visits': [{
                'id': v.id,
                'service': v.get_service_display(),
                'timestamp': v.timestamp.isoformat(),
                'notes': v.notes or '',
                'diagnosis': getattr(v, 'diagnosis', '') or '',
                'prescription_notes': getattr(v, 'prescription_notes', '') or '',
            } for v in visits],
            'latest_doctor': ({
                'diagnosis': getattr(latest_doctor, 'diagnosis', '') or '',
                'prescription_notes': getattr(latest_doctor, 'prescription_notes', '') or '',
                'timestamp': latest_doctor.timestamp.isoformat() if latest_doctor else None,
            } if latest_doctor else None),
            'latest_pharmacy': ({
                'medicines': getattr(latest_pharmacy, 'medicines', '') or '',
                'timestamp': latest_pharmacy.timestamp.isoformat() if latest_pharmacy else None,
            } if latest_pharmacy else None),
        })
    except Patient.DoesNotExist:
        return JsonResponse({
            'error': 'Patient not found. Please scan a valid QR code or use a registered email address.',
            'error_type': 'not_found'
        }, status=404)
