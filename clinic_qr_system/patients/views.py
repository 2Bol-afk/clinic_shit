from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
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
from django.utils.text import slugify
from django.contrib.auth import login as auth_login, authenticate
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.contrib.auth.views import LoginView
from django.http import HttpResponseForbidden
from clinic_qr_system.email_utils import send_patient_registration_email

from .forms import PatientRegistrationForm, PatientSignupForm, AdminPatientForm, PatientAccountForm, PatientPasswordChangeForm, PatientDeleteForm
from .models import Patient


def _generate_patient_code() -> str:
    return uuid.uuid4().hex[:10].upper()


def signup(request):
    if request.method == 'POST':
        form = PatientSignupForm(request.POST, request.FILES)
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
                # Generate username from full name, ensure uniqueness
                base_username = slugify(patient.full_name) or 'user'
                candidate = base_username[:150]
                i = 1
                while User.objects.filter(username=candidate).exists():
                    suffix = str(i)
                    candidate = (base_username[: max(1, 150 - len(suffix))] + suffix)
                    i += 1
                username = candidate
                password = form.cleaned_data['password']
                user = User.objects.create_user(username=username, email=patient.email, password=password)
                patient.user = user
                patient.save(update_fields=['user'])

                # Assign default profile photo if none uploaded
                if not patient.profile_photo:
                    try:
                        from django.core.files.base import ContentFile
                        import requests
                        default_url = 'https://res.cloudinary.com/dkuzneqb8/image/upload/v1758734296/Generated_Image_September_25_2025_-_1_16AM_znxhv6.png'
                        resp = requests.get(default_url, timeout=10)
                        if resp.ok:
                            patient.profile_photo.save('default_profile.png', ContentFile(resp.content), save=True)
                    except Exception:
                        pass
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)
            # Email QR and confirmation using Brevo
            try:
                if patient.email:
                    # Prepare QR code data
                    qr_data = None
                    qr_filename = file_name
                    
                    # Read via storage, not filesystem path
                    try:
                        if patient.qr_code:
                            with patient.qr_code.open('rb') as f:
                                qr_data = f.read()
                    except Exception:
                        qr_data = None
                    if not qr_data and buffer:
                        qr_data = buffer.getvalue()
                    
                    # Send email using Brevo utility
                    sent = send_patient_registration_email(
                        patient_name=patient.full_name,
                        patient_code=patient.patient_code,
                        patient_email=patient.email,
                        qr_code_data=qr_data,
                        qr_filename=qr_filename,
                        username=username
                    )
                    
                    if sent:
                        messages.success(request, f'Confirmation email sent to {patient.email} via Brevo.')
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
    # Render using the registration template with proper multipart form
    return render(request, 'patients/register.html', {'form': form})


def register(request):
    if request.method == 'POST':
        form = PatientRegistrationForm(request.POST, request.FILES)
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
                # Generate username from full name, ensure uniqueness
                base_username = slugify(patient.full_name) or 'user'
                candidate = base_username[:150]
                i = 1
                while User.objects.filter(username=candidate).exists():
                    suffix = str(i)
                    candidate = (base_username[: max(1, 150 - len(suffix))] + suffix)
                    i += 1
                username = candidate
                temp_password = uuid.uuid4().hex[:12]
                user = User.objects.create_user(username=username, email=patient.email, password=temp_password)
                patient.user = user
                patient.must_change_password = True
                patient.save(update_fields=['user','must_change_password'])

                # Assign default profile photo if none uploaded
                if not patient.profile_photo:
                    try:
                        from django.core.files.base import ContentFile
                        import requests
                        default_url = 'https://res.cloudinary.com/dkuzneqb8/image/upload/v1758734296/Generated_Image_September_25_2025_-_1_16AM_znxhv6.png'
                        resp = requests.get(default_url, timeout=10)
                        if resp.ok:
                            patient.profile_photo.save('default_profile.png', ContentFile(resp.content), save=True)
                    except Exception:
                        pass
                # Ensure Patient group exists and add user
                group, _ = Group.objects.get_or_create(name='Patient')
                user.groups.add(group)

            # Email QR code + credentials using Brevo
            try:
                if patient.email:
                    # Prepare QR code data
                    qr_data = None
                    qr_filename = file_name
                    
                    try:
                        if patient.qr_code:
                            with patient.qr_code.open('rb') as f:
                                qr_data = f.read()
                    except Exception:
                        qr_data = None
                    if not qr_data and buffer:
                        qr_data = buffer.getvalue()
                    
                    # Send email using Brevo utility
                    sent = send_patient_registration_email(
                        patient_name=patient.full_name,
                        patient_code=patient.patient_code,
                        patient_email=patient.email,
                        qr_code_data=qr_data,
                        qr_filename=qr_filename,
                        temp_password=temp_password,
                        username=username
                    )
                    
                    if sent:
                        messages.success(request, f'Confirmation email sent to {patient.email} via Brevo.')
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
    from visits.models import VaccinationRecord as VR
    vaccination_records = VR.objects.filter(patient=patient).order_by('-created_at')
    # Vaccinations app records (for accurate dose counts)
    try:
        from vaccinations.models import PatientVaccination
        patient_vaccinations = (PatientVaccination.objects
                                .filter(patient=patient)
                                .select_related('vaccine_type')
                                .prefetch_related('doses')
                                .order_by('-created_at'))
    except Exception:
        patient_vaccinations = []
    context = {
        'patient': patient,
        'visits': visits,
        'doctor_visits': doctor_visits[:10],
        'lab_visits': lab_visits,
        'vaccination_records': vaccination_records,
        'active_prescriptions': active_prescriptions,
        'patient_vaccinations': patient_vaccinations,
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
    writer.writerow(['Patient', 'Code', 'Service', 'Timestamp', 'Staff'])
    for v in visits:
        writer.writerow([
            v.patient.full_name,
            v.patient.patient_code,
            v.get_service_display(),
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
            'Timestamp': v.timestamp.replace(tzinfo=None),
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
    # Ensure QR code exists (self-registered users should already have it; regenerate if missing)
    if not patient.qr_code:
        try:
            file_name = f"qr_{patient.patient_code}.png"
            qr_payload = f"email:{patient.email};id:{patient.id}"
            qr_img = qrcode.make(qr_payload)
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=True)
        except Exception:
            pass

    visits = patient.visits.order_by('-timestamp')
    # Extract latest doctor prescription and pharmacy dispenses
    latest_doctor = visits.filter(service='doctor').first()
    latest_pharmacy = visits.filter(service='pharmacy').first()
    
    # Get detailed prescriptions
    from visits.models import Prescription
    prescriptions = Prescription.objects.filter(
        visit__patient=patient
    ).select_related('doctor', 'dispensed_by').prefetch_related('medicines').order_by('-created_at')
    
    # Vaccination next dose (Dose 2/3/Booster) if not done
    vacc_next = None
    try:
        from vaccinations.models import PatientVaccination
        pv_list = (PatientVaccination.objects
                   .filter(patient=patient)
                   .prefetch_related('doses', 'vaccine_type') )
        for pv in pv_list:
            # find the earliest unadministered dose
            next_dose = None
            for d in sorted(pv.doses.all(), key=lambda x: (x.dose_number or 0, x.scheduled_date or None)):
                if not d.administered:
                    next_dose = d
                    break
            if next_dose:
                label = f"Dose {next_dose.dose_number}" if (next_dose.dose_number or 0) <= 3 else 'Booster'
                vacc_next = {
                    'vaccine_name': pv.vaccine_type.name,
                    'label': label,
                    'scheduled_date': next_dose.scheduled_date,
                }
                break
    except Exception:
        # Fallback using VaccinationRecord details JSON
        try:
            from visits.models import VaccinationRecord
            rec = (VaccinationRecord.objects
                   .filter(patient=patient)
                   .order_by('-created_at')
                   .first())
            if rec and isinstance(rec.details, dict):
                doses = rec.details.get('doses') or []
                # find first unchecked dose with a date
                for d in doses:
                    if not d.get('checked'):
                        lbl = str(d.get('label',''))
                        vacc_next = {
                            'vaccine_name': str(rec.vaccine_type),
                            'label': lbl,
                            'scheduled_date': d.get('date'),
                        }
                        break
        except Exception:
            pass

    # Pending lab processes
    lab_pending = visits.filter(service='lab').filter(status__in=['queued','claimed','in_process'])[:3]

    context = {
        'patient': patient,
        'visits': visits,
        'latest_doctor': latest_doctor,
        'latest_pharmacy': latest_pharmacy,
        'prescriptions': prescriptions,
        'vacc_next': vacc_next,
        'lab_pending': lab_pending,
    }
    return render(request, 'patients/portal_home.html', context)


# Removed PatientPasswordChangeView to prevent account selection issues
# Using custom patient_password_change view instead


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
        # Set new password and log the user out, then redirect to login
        user = request.user
        user.set_password(pwd)
        user.save()
        patient.must_change_password = False
        patient.save(update_fields=['must_change_password'])
        try:
            auth_logout(request)
        except Exception:
            pass
        messages.success(request, 'Password updated. Please log in with your new password.')
        return redirect('/accounts/login/')
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

    # If it's not an email, treat it as a possible patient code
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    is_email = bool(re.match(email_pattern, email))

    try:
        if is_email:
            patient = Patient.objects.get(email__iexact=email)
        else:
            # Treat provided value as patient_code (case-insensitive)
            patient = Patient.objects.get(patient_code__iexact=email)
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
                'profile_photo_url': patient.profile_photo.url if patient.profile_photo else None,
            },
            'visits': [{
                'id': v.id,
                'service': v.get_service_display(),
                'timestamp': v.timestamp.isoformat(),
                'status': v.status,
                'queue_number': getattr(v, 'queue_number', None),
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
            'error': 'Patient not found. Please scan a valid QR code or use a registered email address or patient code.',
            'error_type': 'not_found'
        }, status=404)


@login_required
def qr_code_download(request):
    """Download the patient's QR code as a PNG file"""
    try:
        patient = request.user.patient_profile
    except Patient.DoesNotExist:
        raise Http404("Patient profile not found")
    
    if not patient.qr_code:
        raise Http404("QR code not available for this patient")
    
    # Get the QR code file path
    qr_code_path = patient.qr_code.path
    
    # Check if file exists
    if not os.path.exists(qr_code_path):
        raise Http404("QR code file not found")
    
    # Read the file and create response
    with open(qr_code_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="{patient.patient_code}_qr_code.png"'
        return response


# Admin Patient Management Views
@login_required
def admin_patient_add(request):
    """Admin view to add new patients"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    
    if request.method == 'POST':
        form = AdminPatientForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Create user account
                user = User.objects.create_user(
                    username=form.cleaned_data['email'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data.get('password', 'temp123')
                )
                
                # Create patient
                patient = form.save(commit=False)
                patient.user = user
                patient.patient_code = _generate_patient_code()
                patient.save()
                
                # Generate QR code
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(patient.email)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Save QR code
                buffer = BytesIO()
                img.save(buffer, format='PNG')
                filename = f'qr_{patient.patient_code}.png'
                patient.qr_code.save(filename, ContentFile(buffer.getvalue()), save=True)
                
                messages.success(request, f'Patient {patient.full_name} added successfully!')
                return redirect('admin_patient_list')
    else:
        form = AdminPatientForm()
    
    return render(request, 'patients/admin_patient_form.html', {
        'form': form,
        'title': 'Add New Patient',
        'action': 'Add'
    })


@login_required
def admin_patient_edit(request, pk):
    """Admin view to edit patients"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    
    patient = get_object_or_404(Patient, pk=pk)
    
    if request.method == 'POST':
        form = AdminPatientForm(request.POST, instance=patient)
        if form.is_valid():
            with transaction.atomic():
                # Update patient
                patient = form.save()
                
                # Update user if password provided
                if form.cleaned_data.get('password'):
                    patient.user.set_password(form.cleaned_data['password'])
                    patient.user.save()
                
                messages.success(request, f'Patient {patient.full_name} updated successfully!')
                return redirect('admin_patient_list')
    else:
        form = AdminPatientForm(instance=patient)
    
    return render(request, 'patients/admin_patient_form.html', {
        'form': form,
        'patient': patient,
        'title': f'Edit {patient.full_name}',
        'action': 'Update'
    })


@login_required
def admin_patient_delete(request, pk):
    """Admin view to delete patients"""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access denied")
    
    patient = get_object_or_404(Patient, pk=pk)
    
    if request.method == 'POST':
        patient_name = patient.full_name
        # Delete associated user if exists
        if patient.user:
            patient.user.delete()
        else:
            patient.delete()
        
        messages.success(request, f'Patient {patient_name} deleted successfully!')
        return redirect('admin_patient_list')
    
    return render(request, 'patients/admin_patient_delete.html', {
        'patient': patient
    })


# Patient Account Management Views
@login_required
def patient_account_edit(request):
    """Patient view to edit their own account details - automatically applies to logged-in user only"""
    # Security check: Ensure user has a patient profile
    try:
        patient = request.user.patient_profile
    except Patient.DoesNotExist:
        messages.error(request, 'Patient profile not found. Please contact support.')
        return redirect('patient_portal')
    
    # Additional security: Ensure user is in Patient group
    if not request.user.groups.filter(name='Patient').exists():
        messages.error(request, 'Access denied. Only patients can edit their accounts.')
        return redirect('patient_portal')
    
    if request.method == 'POST':
        form = PatientAccountForm(request.POST, request.FILES, instance=patient)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Store old values for comparison
                    old_email = patient.email
                    old_name = patient.full_name
                    old_photo = patient.profile_photo
                    
                    # Save the updated patient
                    patient = form.save()
                    
                    # Update the associated User account if name changed
                    if old_name != patient.full_name:
                        request.user.first_name = patient.full_name.split()[0] if patient.full_name.split() else patient.full_name
                        request.user.last_name = ' '.join(patient.full_name.split()[1:]) if len(patient.full_name.split()) > 1 else ''
                        request.user.save()
                    
                    # Handle email changes - regenerate QR code and send email
                    if old_email != patient.email:
                        # Update user email
                        request.user.email = patient.email
                        request.user.save()
                        
                        # Generate new QR code
                        qr = qrcode.QRCode(version=1, box_size=10, border=5)
                        qr.add_data(patient.email)
                        qr.make(fit=True)
                        img = qr.make_image(fill_color="black", back_color="white")
                        
                        # Save new QR code
                        buffer = BytesIO()
                        img.save(buffer, format='PNG')
                        filename = f'qr_{patient.patient_code}.png'
                        
                        # Delete old QR code if it exists
                        if patient.qr_code:
                            try:
                                patient.qr_code.delete(save=False)
                            except:
                                pass  # Ignore if file doesn't exist
                        
                        patient.qr_code.save(filename, ContentFile(buffer.getvalue()), save=True)
                        
                        # Send QR code to new email
                        try:
                            send_patient_registration_email(
                                patient_name=patient.full_name,
                                patient_code=patient.patient_code,
                                patient_email=patient.email,
                                qr_code_data=buffer.getvalue(),
                                qr_filename=filename
                            )
                            messages.success(request, 'Account updated successfully! Your new QR code has been sent to your updated email address.')
                        except Exception as e:
                            messages.warning(request, f'Account updated, but failed to send QR code: {str(e)}')
                    else:
                        # Handle profile photo updates
                        if old_photo != patient.profile_photo and patient.profile_photo:
                            # Delete old photo if it exists and is different
                            if old_photo and old_photo != patient.profile_photo:
                                try:
                                    old_photo.delete(save=False)
                                except:
                                    pass  # Ignore if file doesn't exist
                            messages.success(request, 'Account updated successfully! Your profile photo has been updated.')
                        else:
                            messages.success(request, 'Account updated successfully!')
                    
                    return redirect('patient_portal')
                    
            except Exception as e:
                messages.error(request, f'An error occurred while updating your account: {str(e)}')
                return render(request, 'patients/patient_account_edit.html', {
                    'form': form,
                    'patient': patient
                })
    else:
        form = PatientAccountForm(instance=patient)
    
    return render(request, 'patients/patient_account_edit.html', {
        'form': form,
        'patient': patient
    })


@login_required
def patient_password_change(request):
    """Patient view to change their password - automatically applies to logged-in user only"""
    # Security check: Ensure user has a patient profile
    try:
        patient = request.user.patient_profile
    except Patient.DoesNotExist:
        messages.error(request, 'Patient profile not found. Please contact support.')
        return redirect('patient_portal')
    
    # Additional security: Ensure user is in Patient group
    if not request.user.groups.filter(name='Patient').exists():
        messages.error(request, 'Access denied. Only patients can change their passwords.')
        return redirect('patient_portal')
    
    if request.method == 'POST':
        form = PatientPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Update the password for the logged-in user
                    request.user.set_password(form.cleaned_data['new_password'])
                    request.user.save()
                    
                    # Update patient's must_change_password flag
                    patient.must_change_password = False
                    patient.save()
                    
                    messages.success(request, 'Password changed successfully! You can now use your new password to log in.')
                    return redirect('patient_portal')
                    
            except Exception as e:
                messages.error(request, f'An error occurred while changing your password: {str(e)}')
                return render(request, 'patients/patient_password_change.html', {
                    'form': form,
                    'patient': patient
                })
    else:
        form = PatientPasswordChangeForm(request.user)
    
    return render(request, 'patients/patient_password_change.html', {
        'form': form,
        'patient': patient
    })


@login_required
def patient_account_delete(request):
    """Patient view to delete their own account - automatically applies to logged-in user only"""
    # Security check: Ensure user has a patient profile
    try:
        patient = request.user.patient_profile
    except Patient.DoesNotExist:
        messages.error(request, 'Patient profile not found. Please contact support.')
        return redirect('patient_portal')
    
    # Additional security: Ensure user is in Patient group
    if not request.user.groups.filter(name='Patient').exists():
        messages.error(request, 'Access denied. Only patients can delete their accounts.')
        return redirect('patient_portal')
    
    if request.method == 'POST':
        form = PatientDeleteForm(request.user, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    patient_name = patient.full_name
                    
                    # Clean up files before deletion
                    if patient.profile_photo:
                        try:
                            patient.profile_photo.delete(save=False)
                        except:
                            pass  # Ignore if file doesn't exist
                    
                    if patient.qr_code:
                        try:
                            patient.qr_code.delete(save=False)
                        except:
                            pass  # Ignore if file doesn't exist
                    
                    # Delete the user account (this will cascade to patient due to CASCADE)
                    request.user.delete()
                    messages.success(request, f'Account for {patient_name} has been permanently deleted.')
                    return redirect('accounts_login')
                    
            except Exception as e:
                messages.error(request, f'An error occurred while deleting your account: {str(e)}')
                return render(request, 'patients/patient_account_delete.html', {
                    'form': form,
                    'patient': patient
                })
    else:
        form = PatientDeleteForm(request.user)
    
    return render(request, 'patients/patient_account_delete.html', {
        'form': form,
        'patient': patient
    })
