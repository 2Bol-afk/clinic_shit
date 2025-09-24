from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Q
from patients.models import Patient, Doctor
from visits.models import Visit, ServiceType, LabResult, Laboratory, VaccinationRecord, VaccinationType
from vaccinations.models import VaccinationReminder
from visits.forms import LabResultForm, VaccinationForm
from django.contrib.auth.models import Group, User
from django.utils.text import slugify
from .models import ActivityLog
from patients.forms import DoctorForm, DoctorPasswordChangeForm
from django import forms
from django.contrib import messages
from django.core.mail import EmailMessage
from django.conf import settings
from io import BytesIO
from django.core.files.base import ContentFile
import qrcode
from django.views.decorators.http import require_POST
import re
import logging
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.http import JsonResponse
import re
import threading
import csv
import os
from django.core.mail import send_mail
from clinic_qr_system.email_utils import send_test_email, send_patient_registration_email
try:
    from openpyxl import Workbook
except Exception:
    Workbook = None
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash


logger = logging.getLogger(__name__)


def is_admin(user):
    return user.is_superuser


def is_reception(user):
    return user.is_superuser or user.groups.filter(name='Reception').exists()
@login_required
@user_passes_test(lambda u: u.is_superuser)
def send_test_email_view(request):
    to = request.GET.get('to') or os.getenv('TEST_EMAIL_TO') or settings.DEFAULT_FROM_EMAIL
    try:
        sent = send_test_email(
            recipient_email=to,
            message='Hello from Clinic QR System using Brevo email service.',
            subject='Brevo SMTP Test'
        )
        if sent:
            messages.success(request, f'Email sent successfully to {to} via Brevo.')
        else:
            messages.warning(request, f'No email was sent to {to}.')
    except Exception as e:
        messages.error(request, f'Email send failed: {e}')
    return redirect(request.META.get('HTTP_REFERER') or 'admin_dashboard')

@login_required
def index(request):
    # Redirect to role-specific dashboard
    if request.user.is_superuser:
        return redirect('admin_dashboard')  # Redirect admin users to Admin Panel
    
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
    
    # Fallback for users without specific roles
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
            return redirect('admin_dashboard')  # Redirect to Admin Panel directly
        elif request.user.groups.filter(name='Reception').exists():
            return redirect('dashboard_reception')
        elif request.user.groups.filter(name='Doctor').exists():
            # Check if doctor needs to change password
            try:
                doctor = request.user.doctor_profile
                if doctor.must_change_password:
                    return redirect('doctor_password_change')
            except Doctor.DoesNotExist:
                pass
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


class VisitEditForm(forms.Form):
    """Form for editing visit details in reception dashboard"""
    visit_type = forms.ChoiceField(
        choices=[
            ('consultation', 'Consultation'),
            ('laboratory', 'Laboratory'),
            ('vaccination', 'Vaccination')
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'placeholder': 'Select visit type',
            'required': True
        }),
        required=True,
        label='Visit Type'
    )
    department = forms.ChoiceField(
        choices=[
            ('', 'No Department'),
            ('Pediatrics', 'Pediatrics (Children\'s Health)'),
            ('OB-GYN', 'Obstetrics and Gynecology (OB-GYN)'),
            ('Cardiology', 'Cardiology (Heart Care)'),
            ('Radiology', 'Radiology'),
            ('Surgery', 'Surgery'),
            ('Dermatology', 'Dermatology (Skin Care)'),
            ('ENT', 'ENT (Ear, Nose, Throat)')
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'placeholder': 'Select department (optional)'
        }),
        required=False,
        label='Department'
    )

    def __init__(self, *args, **kwargs):
        self.visit = kwargs.pop('visit', None)
        super().__init__(*args, **kwargs)
        
        if self.visit:
            # Check if visit is claimed - disable form if claimed
            if self.visit.status == 'claimed' or self.visit.claimed_by:
                for field in self.fields.values():
                    field.widget.attrs['disabled'] = True
                    field.widget.attrs['readonly'] = True
            
            # Set initial values based on visit data
            if self.visit.department:
                self.fields['visit_type'].initial = 'consultation'
            elif self.visit.notes and 'vaccination' in self.visit.notes.lower():
                self.fields['visit_type'].initial = 'vaccination'
            elif self.visit.notes and 'laboratory' in self.visit.notes.lower():
                self.fields['visit_type'].initial = 'laboratory'
            else:
                self.fields['visit_type'].initial = 'consultation'
            
            self.fields['department'].initial = self.visit.department
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Prevent form submission if visit is claimed
        if self.visit and (self.visit.status == 'claimed' or self.visit.claimed_by):
            raise forms.ValidationError('Cannot edit claimed visits. This visit has been claimed by another staff member.')
        
        return cleaned_data


class WalkInForm(forms.Form):
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter patient\'s full name',
            'required': True
        }),
        required=True
    )
    age = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter patient\'s age',
            'min': '0',
            'max': '150',
            'required': True
        }),
        required=True
    )
    address = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Enter patient\'s complete address',
            'rows': 3,
            'required': True
        }),
        required=True
    )
    contact = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter contact number',
            'required': True
        }),
        required=True
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter email address',
            'required': True
        }),
        required=True
    )
    profile_photo = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
            'capture': 'environment',
            'required': False
        }),
        required=False
    )
    reception_visit_type = forms.ChoiceField(
        choices=[('consultation','Consultation'),('laboratory','Laboratory'),('vaccination','Vaccination')],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'placeholder': 'Select visit type',
            'required': True
        }),
        required=True
    )
    department = forms.ChoiceField(
        choices=Visit.Department.choices,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'placeholder': 'Select department (optional)'
        }),
        required=False
    )


@login_required
@user_passes_test(is_reception)
def reception_walkin(request):
    # Handle pre-selected patient from QR scan
    patient_id = request.GET.get('patient_id')
    pre_selected_patient = None
    if patient_id:
        try:
            pre_selected_patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            pass
    
    if request.method == 'POST':
        form = WalkInForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                    data = form.cleaned_data
                    # If patient was pre-selected, use that patient
                    if pre_selected_patient:
                        patient = pre_selected_patient
                    else:
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
                            # Save uploaded profile photo if provided, else set default
                            uploaded_photo = data.get('profile_photo')
                            if uploaded_photo:
                                patient.profile_photo = uploaded_photo
                                patient.save(update_fields=['profile_photo'])
                            else:
                                # Assign default profile photo URL stored on Cloudinary
                                try:
                                    from django.core.files.base import ContentFile
                                    import requests
                                    default_url = 'https://res.cloudinary.com/dkuzneqb8/image/upload/v1758734296/Generated_Image_September_25_2025_-_1_16AM_znxhv6.png'
                                    resp = requests.get(default_url, timeout=10)
                                    if resp.ok:
                                        patient.profile_photo.save('default_profile.png', ContentFile(resp.content), save=True)
                                except Exception:
                                    pass
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
                                # Generate username from full name, ensure uniqueness
                                base_username = slugify(patient.full_name) or 'user'
                                candidate = base_username[:150]
                                i = 1
                                while User.objects.filter(username=candidate).exists():
                                    suffix = str(i)
                                    candidate = (base_username[: max(1, 150 - len(suffix))] + suffix)
                                    i += 1
                                username = candidate
                                user = User.objects.create_user(username=username, email=patient.email, password=temp_password)
                                # Ensure email is set for email/username auth
                                if user.email != patient.email:
                                    user.email = patient.email
                                    user.save(update_fields=['email'])
                                patient.user = user
                                # Flag for force password change if model supports it
                                if hasattr(patient, 'must_change_password'):
                                    patient.must_change_password = True
                                    patient.save(update_fields=['user','must_change_password'])
                                else:
                                    patient.save(update_fields=['user'])
                                group, _ = Group.objects.get_or_create(name='Patient')
                                user.groups.add(group)
                            except Exception:
                                temp_password = None
                        else:
                            # Existing patient path: ensure linked user has correct email for email-based login
                            if patient and patient.user:
                                try:
                                    if patient.user.email != (patient.email or ''):
                                        patient.user.email = patient.email or ''
                                        patient.user.save(update_fields=['email'])
                                except Exception:
                                    pass
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
                                    # Generate username from full name, ensure uniqueness
                                    base_username = slugify(existing.full_name) or 'user'
                                    candidate = base_username[:150]
                                    i = 1
                                    while User.objects.filter(username=candidate).exists():
                                        suffix = str(i)
                                        candidate = (base_username[: max(1, 150 - len(suffix))] + suffix)
                                        i += 1
                                    username = candidate
                                    user = User.objects.create_user(username=username, email=existing.email, password=temp_password)
                                    existing.user = user
                                    if hasattr(existing, 'must_change_password'):
                                        existing.must_change_password = True
                                        existing.save(update_fields=['user','must_change_password'])
                                    else:
                                        existing.save(update_fields=['user'])
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
                    visit = Visit.objects.create(**kwargs)
            
            # Send queue notification email
            try:
                if patient.email:
                    from clinic_qr_system.email_utils import send_queue_notification_email_html
                    
                    # Determine service type for email
                    if visit_type == 'consultation':
                        service_type = 'consultation'
                        department = data.get('department', '')
                    elif visit_type == 'laboratory':
                        service_type = 'laboratory'
                        department = None
                    elif visit_type == 'vaccination':
                        service_type = 'vaccination'
                        department = None
                    else:
                        service_type = visit_type
                        department = data.get('department', '')
                    
                    # Send queue notification email
                    email_sent = send_queue_notification_email_html(
                        patient_name=patient.full_name,
                        patient_email=patient.email,
                        queue_number=visit.queue_number,
                        service_type=service_type,
                        department=department,
                        visit_id=visit.id
                    )
                    
                    if email_sent:
                        messages.success(request, f'Queue notification email sent to {patient.email}.')
                    else:
                        messages.warning(request, f'Queue notification email failed to send to {patient.email}.')
                        
            except Exception as e:
                messages.error(request, f'Queue notification email failed: {e}')
            
            # Email confirmation with QR attachment using Brevo
            try:
                if patient.email:
                    # Prepare QR code data
                    qr_data = None
                    qr_filename = f"qr_{patient.patient_code}.png"
                    
                    # Open via storage (Cloudinary/local) to avoid absolute path usage
                    try:
                        if patient.qr_code:
                            with patient.qr_code.open('rb') as f:
                                qr_data = f.read()
                    except Exception:
                        qr_data = None
                    if not qr_data and buffer:
                        qr_data = buffer.getvalue() if buffer else None
                    
                    # Send email using Brevo utility
                    sent_now = send_patient_registration_email(
                        patient_name=patient.full_name,
                        patient_code=patient.patient_code,
                        patient_email=patient.email,
                        qr_code_data=qr_data,
                        qr_filename=qr_filename,
                        temp_password=locals().get('temp_password'),
                        username=locals().get('username')
                    )
                    
                    if sent_now:
                        messages.success(request, f'Confirmation email sent to {patient.email} via Brevo.')
                    else:
                        messages.warning(request, f'Confirmation email not sent to {patient.email}.')
            except Exception as e:
                messages.error(request, f'Email send failed: {e}')
            messages.success(request, 'Walk-in patient registered and queued.')
            return redirect('dashboard_reception')
    else:
        form = WalkInForm()
        # Pre-populate form if patient is pre-selected
        if pre_selected_patient:
            form = WalkInForm(initial={
                'full_name': pre_selected_patient.full_name,
                'age': pre_selected_patient.age,
                'address': pre_selected_patient.address,
                'contact': pre_selected_patient.contact,
                'email': pre_selected_patient.email,
            })
    return render(request, 'dashboard/reception_walkin.html', {
        'form': form,
        'pre_selected_patient': pre_selected_patient
    })


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
    # Prevent deleting if any related queue already marked done (same patient, same day)
    same_day = visit.timestamp.date()
    any_done = (Visit.objects
                .filter(patient=visit.patient, timestamp__date=same_day)
                .filter(status=Visit.Status.DONE)
                .exists())
    if request.method == 'POST':
        if any_done or visit.status == Visit.Status.DONE:
            messages.error(request, "This patient's queue has already been marked as done and cannot be deleted.")
            return redirect('dashboard_reception')
        # Cascade delete related, non-done queues across modules for the same day
        from django.db import transaction as _tx
        with _tx.atomic():
            related_qs = (Visit.objects
                          .filter(patient=visit.patient, timestamp__date=same_day)
                          .exclude(pk=visit.pk)
                          .exclude(status=Visit.Status.DONE))
            # Deleting visits will cascade to dependent records via FK on_delete=CASCADE
            related_qs.delete()
            visit.delete()
        messages.success(request, 'Reception entry and related queue entries deleted.')
        return redirect('dashboard_reception')
    return render(request, 'dashboard/reception_delete_confirm.html', {
        'visit': visit,
        'any_done': any_done,
    })


@login_required
def reception_visit_edit(request, pk):
    """Edit visit details in reception dashboard"""
    # Security check: Only reception staff and superusers can edit visits
    if not (request.user.is_superuser or request.user.groups.filter(name='Reception').exists()):
        messages.error(request, 'Access denied. Only reception staff can edit visits.')
        return redirect('dashboard_reception')
    
    visit = get_object_or_404(Visit, pk=pk, service='reception')
    
    # Check if visit is claimed - prevent editing
    if visit.status == 'claimed' or visit.claimed_by:
        messages.error(request, f'Cannot edit claimed visits. This visit has been claimed by {visit.claimed_by.get_full_name() if visit.claimed_by else "another staff member"}.')
        return redirect('dashboard_reception')
    
    if request.method == 'POST':
        form = VisitEditForm(request.POST, visit=visit)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Update visit based on form data
                    visit_type = form.cleaned_data['visit_type']
                    department = form.cleaned_data['department']
                    
                    # Update department
                    visit.department = department if department else ''
                    
                    # Update notes based on visit type
                    if visit_type == 'consultation':
                        visit.notes = ''
                        # Clear service type when switching to consultation
                        visit.service_type = None
                    elif visit_type == 'laboratory':
                        visit.notes = "[Visit: Laboratory]"
                        visit.department = ''
                        # Set service_type to Laboratory if available
                        try:
                            svc = ServiceType.objects.filter(name__iexact='Laboratory').first()
                            visit.service_type = svc
                        except Exception:
                            pass
                    elif visit_type == 'vaccination':
                        visit.notes = "[Visit: Vaccination]"
                        visit.department = ''
                        # Set service_type to Vaccination if available
                        try:
                            svc = ServiceType.objects.filter(name__iexact='Vaccination').first()
                            visit.service_type = svc
                        except Exception:
                            pass
                    
                    visit.save()
                    
                    messages.success(request, f'Visit for {visit.patient.full_name} updated successfully!')
                    return redirect('dashboard_reception')
                    
            except Exception as e:
                messages.error(request, f'An error occurred while updating the visit: {str(e)}')
                return render(request, 'dashboard/reception_visit_edit.html', {
                    'form': form,
                    'visit': visit
                })
    else:
        form = VisitEditForm(visit=visit)
    
    return render(request, 'dashboard/reception_visit_edit.html', {
        'form': form,
        'visit': visit
    })


@login_required
def doctor_password_change(request):
    """Doctor view to change their password - forced on first login"""
    # Security check: Ensure user is a doctor
    if not request.user.groups.filter(name='Doctor').exists():
        messages.error(request, 'Access denied. Only doctors can access this page.')
        return redirect('dashboard_doctor')
    
    try:
        doctor = request.user.doctor_profile
    except Doctor.DoesNotExist:
        messages.error(request, 'Doctor profile not found. Please contact support.')
        return redirect('dashboard_doctor')
    
    if request.method == 'POST':
        form = DoctorPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Update the password for the logged-in user
                    request.user.set_password(form.cleaned_data['new_password'])
                    request.user.save()
                    
                    # Clear the must_change_password flag
                    doctor.must_change_password = False
                    doctor.save()
                    
                    messages.success(request, 'Password changed successfully! You can now access the system.')
                    return redirect('dashboard_doctor')
                    
            except Exception as e:
                messages.error(request, f'An error occurred while changing your password: {str(e)}')
                return render(request, 'dashboard/doctors/password_change.html', {
                    'form': form,
                    'doctor': doctor
                })
    else:
        form = DoctorPasswordChangeForm(request.user)
    
    return render(request, 'dashboard/doctors/password_change.html', {
        'form': form,
        'doctor': doctor
    })


@login_required
def doctor_dashboard(request):
    # Check if doctor needs to change password
    if request.user.groups.filter(name='Doctor').exists():
        try:
            doctor = request.user.doctor_profile
            if doctor.must_change_password:
                return redirect('doctor_password_change')
        except Doctor.DoesNotExist:
            pass
    
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
        
        # Send queue notification email for lab visits
        try:
            if src.patient.email and qn:  # Only send if there's a queue number
                from clinic_qr_system.email_utils import send_queue_notification_email_html
                
                email_sent = send_queue_notification_email_html(
                    patient_name=src.patient.full_name,
                    patient_email=src.patient.email,
                    queue_number=qn,
                    service_type='laboratory',
                    department=None,
                    visit_id=new_visit.id
                )
                
                if email_sent:
                    messages.success(request, f'Lab queue notification email sent to {src.patient.email}.')
                else:
                    messages.warning(request, f'Lab queue notification email failed to send to {src.patient.email}.')
                    
        except Exception as e:
            messages.error(request, f'Lab queue notification email failed: {e}')
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
        
        # Send lab result email to patient
        try:
            from clinic_qr_system.email_utils import send_lab_result_email
            from clinic_qr_system.pdf_utils import generate_lab_result_pdf, generate_lab_result_pdf_simple
            
            # Get patient email
            patient_email = lab_visit.patient.email or lab_visit.patient.user.email
            if patient_email:
                # Generate PDF attachment
                pdf_content = None
                if generate_lab_result_pdf:
                    pdf_content = generate_lab_result_pdf(
                        patient_name=lab_visit.patient.full_name,
                        patient_code=lab_visit.patient.patient_code,
                        lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                        lab_results=lab_visit.lab_results or 'No results available',
                        visit_id=lab_visit.id,
                        completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                        doctor_name=lab_visit.doctor_user.get_full_name() if lab_visit.doctor_user else None
                    )
                
                # Fallback to simple PDF if ReportLab PDF fails
                if not pdf_content:
                    pdf_content = generate_lab_result_pdf_simple(
                        patient_name=lab_visit.patient.full_name,
                        patient_code=lab_visit.patient.patient_code,
                        lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                        lab_results=lab_visit.lab_results or 'No results available',
                        visit_id=lab_visit.id,
                        completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                        doctor_name=lab_visit.doctor_user.get_full_name() if lab_visit.doctor_user else None
                    )
                
                # Prepare attachment data
                attachment_data = None
                if pdf_content:
                    attachment_data = {
                        'filename': f'lab_result_{lab_visit.id}_{lab_visit.patient.patient_code}.pdf',
                        'content': pdf_content,
                        'mimetype': 'application/pdf'
                    }
                
                # Send email
                email_sent = send_lab_result_email(
                    patient_name=lab_visit.patient.full_name,
                    patient_email=patient_email,
                    lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                    lab_results=lab_visit.lab_results or 'No results available',
                    visit_id=lab_visit.id,
                    completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                    attachment_data=attachment_data
                )
                
                if email_sent:
                    messages.success(request, 'Lab marked as done and result email sent to patient.')
                else:
                    messages.warning(request, 'Lab marked as done, but failed to send result email to patient.')
            else:
                messages.warning(request, 'Lab marked as done, but no patient email found for notification.')
        except Exception as e:
            logger.error(f"Failed to send lab result email: {e}")
            messages.warning(request, 'Lab marked as done, but failed to send result email.')
    
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
    p = visit.patient
    return JsonResponse({'success': True, 'patient': {
        'full_name': p.full_name,
        'patient_code': p.patient_code,
        'email': p.email,
        'profile_photo_url': (p.profile_photo.url if p.profile_photo else ''),
    }})


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
            # Send lab result email to patient
            try:
                from clinic_qr_system.email_utils import send_lab_result_email
                from clinic_qr_system.pdf_utils import generate_lab_result_pdf, generate_lab_result_pdf_simple
                
                # Get patient email
                patient_email = lab_visit.patient.email or lab_visit.patient.user.email
                if patient_email:
                    # Generate PDF attachment
                    pdf_content = None
                    if generate_lab_result_pdf:
                        pdf_content = generate_lab_result_pdf(
                            patient_name=lab_visit.patient.full_name,
                            patient_code=lab_visit.patient.patient_code,
                            lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                            lab_results=lab_visit.lab_results or 'No results available',
                            visit_id=lab_visit.id,
                            completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                            doctor_name=lab_visit.doctor_user.get_full_name() if lab_visit.doctor_user else None
                        )
                    
                    # Fallback to simple PDF if ReportLab PDF fails
                    if not pdf_content:
                        pdf_content = generate_lab_result_pdf_simple(
                            patient_name=lab_visit.patient.full_name,
                            patient_code=lab_visit.patient.patient_code,
                            lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                            lab_results=lab_visit.lab_results or 'No results available',
                            visit_id=lab_visit.id,
                            completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                            doctor_name=lab_visit.doctor_user.get_full_name() if lab_visit.doctor_user else None
                        )
                    
                    # Prepare attachment data
                    attachment_data = None
                    if pdf_content:
                        attachment_data = {
                            'filename': f'lab_result_{lab_visit.id}_{lab_visit.patient.patient_code}.pdf',
                            'content': pdf_content,
                            'mimetype': 'application/pdf'
                        }
                    
                    # Send email
                    email_sent = send_lab_result_email(
                        patient_name=lab_visit.patient.full_name,
                        patient_email=patient_email,
                        lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                        lab_results=lab_visit.lab_results or 'No results available',
                        visit_id=lab_visit.id,
                        completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                        attachment_data=attachment_data
                    )
                    
                    if email_sent:
                        messages.success(request, 'Lab marked as done and result email sent to patient.')
                    else:
                        messages.warning(request, 'Lab marked as done, but failed to send result email to patient.')
                else:
                    messages.warning(request, 'Lab marked as done, but no patient email found for notification.')
            except Exception as e:
                logger.error(f"Failed to send lab result email: {e}")
                messages.warning(request, 'Lab marked as done, but failed to send result email.')
            
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
                
                # Send lab result email to patient
                try:
                    from clinic_qr_system.email_utils import send_lab_result_email
                    from clinic_qr_system.pdf_utils import generate_lab_result_pdf, generate_lab_result_pdf_simple
                    
                    # Get patient email
                    patient_email = lab_visit.patient.email or lab_visit.patient.user.email
                    if patient_email:
                        # Generate PDF attachment
                        pdf_content = None
                        if generate_lab_result_pdf:
                            pdf_content = generate_lab_result_pdf(
                                patient_name=lab_visit.patient.full_name,
                                patient_code=lab_visit.patient.patient_code,
                                lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                                lab_results=lab_visit.lab_results or 'No results available',
                                visit_id=lab_visit.id,
                                completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                                doctor_name=lab_visit.doctor_user.get_full_name() if lab_visit.doctor_user else None
                            )
                        
                        # Fallback to simple PDF if ReportLab PDF fails
                        if not pdf_content:
                            pdf_content = generate_lab_result_pdf_simple(
                                patient_name=lab_visit.patient.full_name,
                                patient_code=lab_visit.patient.patient_code,
                                lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                                lab_results=lab_visit.lab_results or 'No results available',
                                visit_id=lab_visit.id,
                                completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                                doctor_name=lab_visit.doctor_user.get_full_name() if lab_visit.doctor_user else None
                            )
                        
                        # Prepare attachment data
                        attachment_data = None
                        if pdf_content:
                            attachment_data = {
                                'filename': f'lab_result_{lab_visit.id}_{lab_visit.patient.patient_code}.pdf',
                                'content': pdf_content,
                                'mimetype': 'application/pdf'
                            }
                        
                        # Send email
                        email_sent = send_lab_result_email(
                            patient_name=lab_visit.patient.full_name,
                            patient_email=patient_email,
                            lab_type=lab_visit.lab_test_type or 'Laboratory Test',
                            lab_results=lab_visit.lab_results or 'No results available',
                            visit_id=lab_visit.id,
                            completed_at=lab_visit.lab_completed_at.strftime('%Y-%m-%d %H:%M:%S'),
                            attachment_data=attachment_data
                        )
                        
                        if email_sent:
                            messages.success(request, 'Lab result saved and email sent to patient.')
                        else:
                            messages.warning(request, 'Lab result saved, but failed to send email to patient.')
                    else:
                        messages.warning(request, 'Lab result saved, but no patient email found for notification.')
                except Exception as e:
                    logger.error(f"Failed to send lab result email: {e}")
                    messages.warning(request, 'Lab result saved, but failed to send email.')
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
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Pharmacy').exists())
def pharmacy_dashboard(request):
    from visits.models import Prescription, PrescriptionMedicine
    from visits.forms import PrescriptionSearchForm
    
    # Get search parameters
    search_form = PrescriptionSearchForm(request.GET)
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base queryset for prescriptions
    prescriptions_qs = Prescription.objects.select_related(
        'visit__patient', 'visit__doctor_user', 'doctor'
    ).prefetch_related('medicines').order_by('-created_at')
    
    # Apply filters
    if search_query:
        prescriptions_qs = prescriptions_qs.filter(
            models.Q(visit__patient__full_name__icontains=search_query) |
            models.Q(doctor__first_name__icontains=search_query) |
            models.Q(doctor__last_name__icontains=search_query) |
            models.Q(medicines__drug_name__icontains=search_query)
        ).distinct()
    
    if status_filter:
        prescriptions_qs = prescriptions_qs.filter(status=status_filter)
    
    if date_from:
        prescriptions_qs = prescriptions_qs.filter(created_at__date__gte=date_from)
    
    if date_to:
        prescriptions_qs = prescriptions_qs.filter(created_at__date__lte=date_to)
    
    # Separate pending and dispensed prescriptions
    pending_prescriptions = prescriptions_qs.filter(status__in=[Prescription.Status.PENDING, Prescription.Status.READY])
    dispensed_prescriptions = prescriptions_qs.filter(status=Prescription.Status.DISPENSED)[:50]
    
    # Statistics
    stats = {
        'total_pending': pending_prescriptions.count(),
        'total_dispensed_today': prescriptions_qs.filter(
            status=Prescription.Status.DISPENSED,
            dispensed_at__date=timezone.localdate()
        ).count(),
        'total_dispensed_week': prescriptions_qs.filter(
            status=Prescription.Status.DISPENSED,
            dispensed_at__date__gte=timezone.localdate() - timezone.timedelta(days=7)
        ).count(),
    }
    
    context = {
        'pending_prescriptions': pending_prescriptions,
        'dispensed_prescriptions': dispensed_prescriptions,
        'search_form': search_form,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'dashboard/pharmacy.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Pharmacy').exists())
def pharmacy_dispense(request, prescription_id):
    """View for dispensing a prescription"""
    from visits.models import Prescription, PrescriptionMedicine
    from visits.forms import PrescriptionDispenseForm, PrescriptionMedicineDispenseForm
    
    prescription = get_object_or_404(Prescription, pk=prescription_id)
    
    if request.method == 'POST':
        form = PrescriptionDispenseForm(request.POST, instance=prescription)
        
        if form.is_valid():
            with transaction.atomic():
                # Update prescription status
                prescription.status = Prescription.Status.DISPENSED
                prescription.dispensed_by = request.user
                prescription.dispensed_at = timezone.now()
                prescription.pharmacy_notes = form.cleaned_data['pharmacy_notes']
                prescription.save()
                
                # Update individual medicines
                for medicine in prescription.medicines.all():
                    dispensed_qty = request.POST.get(f'medicine_{medicine.id}_dispensed_quantity', '').strip()
                    substitution_notes = request.POST.get(f'medicine_{medicine.id}_substitution_notes', '').strip()
                    
                    if dispensed_qty:
                        medicine.dispensed_quantity = dispensed_qty
                    if substitution_notes:
                        medicine.substitution_notes = substitution_notes
                    medicine.save()
                
                # Do not send email on dispense; just confirm action
                messages.success(request, 'Prescription dispensed successfully.')
                
                return redirect('dashboard_pharmacy')
    else:
        form = PrescriptionDispenseForm(instance=prescription)
    
    # Create forms for each medicine
    medicine_forms = []
    for medicine in prescription.medicines.all():
        medicine_form = PrescriptionMedicineDispenseForm(instance=medicine)
        medicine_forms.append((medicine, medicine_form))
    
    context = {
        'prescription': prescription,
        'form': form,
        'medicine_forms': medicine_forms,
    }
    
    return render(request, 'dashboard/pharmacy_dispense.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Pharmacy').exists())
def pharmacy_mark_ready(request, prescription_id):
    """Mark prescription as ready for pickup"""
    from visits.models import Prescription
    
    prescription = get_object_or_404(Prescription, pk=prescription_id)
    
    if prescription.status == Prescription.Status.PENDING:
        prescription.status = Prescription.Status.READY
        prescription.save()
        
        # Send notification email to patient
        try:
            if prescription.visit.patient.email:
                from clinic_qr_system.email_utils import send_notification_email
                
                subject = "Your Prescription is Ready for Pickup"
                message = f"""
Dear {prescription.visit.patient.full_name},

Your prescribed medicines are ready at the Pharmacy. Please proceed to the pharmacy window to collect your medications.

Prescription Details:
- Prescription ID: {prescription.id}
- Doctor: {prescription.doctor.get_full_name() if prescription.doctor else 'Dr. Unknown'}
- Created: {prescription.created_at.strftime('%Y-%m-%d %H:%M')}

Please bring a valid ID when collecting your prescription.

Thank you for choosing our clinic.

Regards,
Clinic Pharmacy
                """.strip()
                
                send_notification_email(
                    recipient_list=[prescription.visit.patient.email],
                    subject=subject,
                    message=message
                )
                
                messages.success(request, f'Prescription marked as ready and notification sent to {prescription.visit.patient.email}.')
            else:
                messages.success(request, 'Prescription marked as ready.')
                
        except Exception as e:
            messages.warning(request, f'Prescription marked as ready but notification email failed: {e}')
    else:
        messages.error(request, 'Only pending prescriptions can be marked as ready.')
    
    return redirect('dashboard_pharmacy')


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
    p = visit.patient
    return JsonResponse({'success': True, 'patient': {
        'full_name': p.full_name,
        'patient_code': p.patient_code,
        'email': p.email,
        'profile_photo_url': (p.profile_photo.url if p.profile_photo else ''),
    }})


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
            # Prefer structured dose plan JSON when provided; only overwrite if valid
            updated_details = None
            dose_plan_raw = request.POST.get('dose_plan_json') or ''
            if dose_plan_raw:
                try:
                    import json
                    parsed = json.loads(dose_plan_raw)
                    if isinstance(parsed, dict) and parsed:
                        updated_details = parsed
                except Exception:
                    updated_details = None
            # If hidden JSON was empty, synthesize plan from checkbox/date fields
            if updated_details is None:
                doses = []
                dose_items = request.POST.getlist('dose_keys[]')  # optional hidden list (not used here)
                # Reconstruct from naming pattern dose[KEY] and date[KEY]
                for key in request.POST:
                    if key.startswith('dose[') and key.endswith(']'):
                        dkey = key[5:-1]
                        checked = True
                        ddate = request.POST.get(f'date[{dkey}]', '')
                        doses.append({'key': dkey, 'label': dkey.replace('_',' ').title(), 'checked': checked, 'date': ddate})
                if doses:
                    updated_details = {
                        'vaccine': form.cleaned_data['vaccine_type'],
                        'doses': doses
                    }
            if updated_details is None:
                # Try to parse textarea details as JSON; if not JSON, keep previous
                try:
                    import json
                    parsed_textarea = json.loads(form.cleaned_data.get('details') or '{}')
                    if isinstance(parsed_textarea, dict) and parsed_textarea:
                        updated_details = parsed_textarea
                except Exception:
                    updated_details = None
            if updated_details is not None:
                vr.details = updated_details
            action = request.POST.get('action')
            # Sync Dose 2/3 into vaccinations app for reminder scheduling
            try:
                from vaccinations.models import VaccineType as VxType, PatientVaccination, VaccineDose, VaccinationReminder
                plan = vr.details if isinstance(vr.details, dict) else {}
                doses = plan.get('doses', [])
                # Map visits.VaccinationType string to vaccinations.VaccineType
                vx = None
                try:
                    vx = VxType.objects.filter(name=str(vr.vaccine_type)).first()
                except Exception:
                    vx = None
                # Create vaccine type on-the-fly if missing
                if not vx:
                    name = str(vr.vaccine_type)
                    total = 2
                    lname = name.lower()
                    if 'polio' in lname:
                        total = 4
                    elif 'hepatitis b' in lname:
                        total = 3
                    elif 'hpv' in lname:
                        total = 3
                    elif 'tetanus' in lname:
                        total = 3
                    vx = VxType.objects.create(name=name, description='', total_doses_required=total, dose_intervals=[])
                if vx:
                    pv, _ = PatientVaccination.objects.get_or_create(
                        patient=vacc_visit.patient,
                        vaccine_type=vx,
                        defaults={
                            'started_date': timezone.localdate(),
                            'created_by': request.user
                        }
                    )
                    for d in doses:
                        label = str(d.get('label', ''))
                        date_str = (d.get('date') or '').strip()
                        dose_number = None
                        if 'Dose 1' in label:
                            dose_number = 1
                        elif 'Dose 2' in label:
                            dose_number = 2
                        elif 'Dose 3' in label:
                            dose_number = 3
                        if dose_number is None:
                            continue
                        try:
                            from datetime import date as _date
                            sched_date = _date.fromisoformat(date_str) if date_str else timezone.localdate()
                        except Exception:
                            sched_date = timezone.localdate()
                        dose_obj, _ = VaccineDose.objects.get_or_create(
                            vaccination=pv,
                            dose_number=dose_number,
                            defaults={'scheduled_date': sched_date, 'administered': False}
                        )
                        # If date changed, update
                        if dose_obj.scheduled_date != sched_date:
                            dose_obj.scheduled_date = sched_date
                            dose_obj.administered = bool(d.get('checked')) and (action == 'done')
                            dose_obj.save(update_fields=['scheduled_date', 'administered'])
                        # Reflect administered state when the checkbox is checked (counts progress as given)
                        if d.get('checked'):
                            if not dose_obj.administered:
                                dose_obj.administered = True
                                dose_obj.administered_by = request.user
                                dose_obj.administered_date = timezone.localdate()
                                dose_obj.save(update_fields=['administered','administered_by','administered_date'])
                        # Ensure there is a pending reminder record for tracking (optional)
                        if not VaccinationReminder.objects.filter(dose=dose_obj, reminder_date=sched_date).exists():
                            VaccinationReminder.objects.create(dose=dose_obj, reminder_date=sched_date, sent=False)
                    # After syncing doses, update completion flag
                    try:
                        total_required = vx.total_doses_required or 1
                        administered_count = pv.doses.filter(administered=True).count()
                        if administered_count >= total_required:
                            pv.completed = True
                            pv.completion_date = timezone.localdate()
                        else:
                            pv.completed = False
                            pv.completion_date = None
                        pv.save(update_fields=['completed', 'completion_date'])
                    except Exception:
                        pass
            except Exception as _sync_err:
                logger.warning(f"Vaccination reminder sync failed: {_sync_err}")
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
                # Immediately email patient with planned Dose 2/3 dates
                try:
                    from clinic_qr_system.email_utils import send_notification_email
                    patient = vacc_visit.patient
                    plan = vr.details if isinstance(vr.details, dict) else {}
                    doses = plan.get('doses', [])
                    vax_name = str(vr.vaccine_type)
                    dose2 = next((d for d in doses if str(d.get('label','')).lower().startswith('dose 2')), None)
                    dose3 = next((d for d in doses if str(d.get('label','')).lower().startswith('dose 3')), None)
                    boosters = [d for d in doses if str(d.get('label','')).lower().startswith('booster')]
                    d2_date = (dose2.get('date') if dose2 else '') or '—'
                    d3_date = (dose3.get('date') if dose3 else '') or '—'
                    booster_lines = []
                    for b in boosters:
                        b_label = str(b.get('label','Booster'))
                        b_date = (b.get('date') or '—')
                        booster_lines.append(f"- {b_label} date: {b_date}")
                    booster_text = ("\n" + "\n".join(booster_lines)) if booster_lines else ''
                    subject = f"{patient.full_name}: Next doses for {vax_name}"
                    plain = (
                        f"Hello {patient.full_name},\n\n"
                        f"Here are your planned next doses for {vax_name}:\n"
                        f"- Dose 2 date: {d2_date}\n"
                        f"- Dose 3 date: {d3_date}{booster_text}\n\n"
                        f"If these dates need changes, please contact the clinic.\n\n"
                        f"Regards,\nClinic QR System"
                    )
                    html = (
                        f"<html><body style='font-family: Arial, sans-serif;'>"
                        f"<h3>Vaccination Plan</h3>"
                        f"<p>Hello <strong>{patient.full_name}</strong>,</p>"
                        f"<p>Here are your planned next doses for <strong>{vax_name}</strong>:</p>"
                        f"<ul>"
                        f"<li><strong>Dose 2:</strong> {d2_date}</li>"
                        f"<li><strong>Dose 3:</strong> {d3_date}</li>"
                        f"{''.join([f'<li><strong>{str(b.get('label','Booster'))}:</strong> {str(b.get('date') or '—')}</li>' for b in boosters])}"
                        f"</ul>"
                        f"<p>If these dates need changes, please contact the clinic.</p>"
                        f"<p>Regards,<br>Clinic QR System</p>"
                        f"</body></html>"
                    )
                    if patient and patient.email:
                        send_notification_email([patient.email], subject, plain, html)
                except Exception as e:
                    logger.warning(f"Failed to send immediate vaccination plan email: {e}")
            else:
                vr.status = 'in_process'
                vacc_visit.status = Visit.Status.IN_PROCESS
                vacc_visit.save(update_fields=['status'])
            vr.administered_by = request.user
            vr.save()
            # Schedule reminders for Dose 2/3 if dates set
            try:
                from vaccinations.models import VaccinationReminder
                plan = vr.details if isinstance(vr.details, dict) else {}
                doses = plan.get('doses', [])
                # Clear existing unsent reminders for this record to avoid duplicates
                VaccinationReminder.objects.filter(dose__vaccination__patient=vacc_visit.patient).filter(sent=False).delete()
                for d in doses:
                    label = str(d.get('label', ''))
                    date_str = (d.get('date') or '').strip()
                    if not date_str:
                        continue
                    if ('Dose 2' in label) or ('Dose 3' in label):
                        # Note: Full integration would map to VaccineDose. For now, log intent.
                        logger.info(f"Reminder scheduled for {vacc_visit.patient.full_name} · {vr.vaccine_type} · {label} on {date_str}")
            except Exception as e:
                logger.warning(f"Failed to schedule vaccination reminders: {e}")
            messages.success(request, 'Vaccination record saved.')
            # On Not Done, go back to vaccination list as requested
            if action == 'done' or action == 'not_done':
                return redirect('dashboard_vaccination')
            return redirect('vaccination_work', pk=vacc_visit.pk)
    else:
        form = VaccinationForm(instance=vr, initial={'vaccine_type': vr.vaccine_type})
    # Prevent duplicate vaccine type selection for this patient (allow current)
    try:
        existing_types = set(VaccinationRecord.objects.filter(patient=vacc_visit.patient).values_list('vaccine_type', flat=True))
        current = vr.vaccine_type
        if current in existing_types:
            existing_types.remove(current)
        filtered = []
        for val, label in form.fields['vaccine_type'].choices:
            if val in (None, '', '---------'):
                filtered.append((val, label))
                continue
            if val in existing_types:
                continue
            filtered.append((val, label))
        form.fields['vaccine_type'].choices = filtered
    except Exception:
        pass
    return render(request, 'dashboard/vaccination_work.html', {'visit': vacc_visit, 'form': form, 'vacc_record': vr})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Vaccination').exists())
@require_POST
def vaccination_finish(request, pk: int):
    """Finish a vaccination visit"""
    vacc_visit = get_object_or_404(Visit, pk=pk, service='vaccination')
    vr = VaccinationRecord.objects.filter(visit=vacc_visit).order_by('-updated_at').first()
    if not vr:
        vr = VaccinationRecord.objects.create(visit=vacc_visit, patient=vacc_visit.patient, vaccine_type=VaccinationType.COVID19)
    
    # Mark vaccination as done
    vr.status = 'done'
    vr.administered_by = request.user
    vr.save()
    
    # Update visit status
    vacc_visit.status = Visit.Status.DONE
    vacc_visit.vaccination_date = timezone.localdate()
    vacc_visit.save(update_fields=['status', 'vaccination_date'])
    
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
    
    messages.success(request, f'Vaccination completed for {vacc_visit.patient.full_name}.')
    return redirect('dashboard_vaccination')


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Vaccination').exists())
def vaccination_autosave(request, pk: int):
    """Autosave vaccination plan changes (AJAX only)."""
    if request.method != 'POST' or request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
    vacc_visit = get_object_or_404(Visit, pk=pk, service='vaccination')
    vr = VaccinationRecord.objects.filter(visit=vacc_visit).order_by('-updated_at').first()
    if not vr:
        vr = VaccinationRecord.objects.create(visit=vacc_visit, patient=vacc_visit.patient, vaccine_type=VaccinationType.COVID19)
    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
    # Update vaccine type and details
    vaccine = payload.get('vaccine')
    if vaccine:
        vr.vaccine_type = vaccine
    if isinstance(payload, dict):
        vr.details = payload
    vr.status = 'in_process'
    vr.administered_by = request.user
    vr.save()
    return JsonResponse({'success': True})

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
    
    # Role-based filtering
    try:
        user_groups = request.user.groups.values_list('name', flat=True)
        is_pharmacy = 'Pharmacy' in user_groups
        is_doctor = 'Doctor' in user_groups
        is_lab = 'Laboratory' in user_groups
        is_vaccination = 'Vaccination' in user_groups
        is_reception = 'Reception' in user_groups
        is_admin = request.user.is_superuser
    except Exception:
        is_pharmacy = is_doctor = is_lab = is_vaccination = is_reception = is_admin = False
    
    # Apply role-based filtering
    if is_pharmacy and not is_admin:
        # Pharmacy users see only pharmacy-related visits
        qs = qs.filter(service='pharmacy')
    elif is_doctor and not is_admin:
        # Doctor users see only their own consultations
        qs = qs.filter(service='doctor', doctor_user=request.user)
    elif is_lab and not is_admin:
        # Lab users see only lab-related visits
        qs = qs.filter(service='laboratory')
    elif is_vaccination and not is_admin:
        # Vaccination users see only vaccination-related visits
        qs = qs.filter(service='vaccination')
    elif is_reception and not is_admin:
        # Reception users see all visits (they handle all departments)
        pass  # No additional filtering needed
    # Admin/superuser sees all visits (no additional filtering)
    export = request.GET.get('export')
    if export == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="visits.csv"'
        writer = csv.writer(resp)
        writer.writerow(['Date','Service','Patient'])
        for v in qs:
            writer.writerow([v.timestamp.strftime('%Y-%m-%d %H:%M'), v.get_service_display(), v.patient.full_name])
        return resp
    if export == 'xlsx':
        if not Workbook:
            messages.error(request, 'XLSX export is unavailable (openpyxl not installed).')
            return redirect('dashboard_reports')
        wb = Workbook()
        ws = wb.active
        ws.title = 'Visits'
        ws.append(['Date','Service','Patient'])
        for v in qs:
            ws.append([v.timestamp.strftime('%Y-%m-%d %H:%M'), v.get_service_display(), v.patient.full_name])
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
        y -= 14
        p.setFont("Helvetica", 9)
        for v in qs[:500]:
            if y < 40:
                p.showPage()
                y = height - 40
            p.drawString(40, y, v.timestamp.strftime('%Y-%m-%d %H:%M'))
            p.drawString(150, y, v.get_service_display())
            p.drawString(230, y, v.patient.full_name[:22])
            y -= 12
        p.showPage()
        p.save()
        return resp
    return render(request, 'dashboard/reports.html', {'visits': qs, 'start': start or '', 'end': end or '', 'service': service or ''})


@login_required
@user_passes_test(lambda u: u.is_superuser or u.groups.filter(name='Pharmacy').exists())
def pharmacy_reports(request):
    """Pharmacy-specific reports for prescriptions"""
    from visits.models import Prescription, PrescriptionMedicine
    
    # Filters
    start = request.GET.get('start')
    end = request.GET.get('end')
    status = request.GET.get('status')
    doctor = request.GET.get('doctor')
    # Sanitize dates (handle accidental trailing punctuation like a period)
    import re
    def clean_date(value: str) -> str:
        if not value:
            return ''
        value = value.strip()
        m = re.match(r'^(\d{4}-\d{2}-\d{2})', value)
        if m:
            return m.group(1)
        # Fallback: remove trailing non-date chars
        return re.sub(r'[^0-9\-]', '', value)[:10]
    start = clean_date(start)
    end = clean_date(end)
    
    # Base queryset
    qs = Prescription.objects.select_related(
        'visit__patient', 'visit__doctor_user', 'doctor', 'dispensed_by'
    ).prefetch_related('medicines').order_by('-created_at')
    
    # Apply filters
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    if status:
        qs = qs.filter(status=status)
    if doctor:
        qs = qs.filter(doctor__id=doctor)
    
    # Export functionality
    export = request.GET.get('export')
    if export == 'csv':
        import csv
        from django.http import HttpResponse
        resp = HttpResponse(content_type='text/csv')
        filename = f"pharmacy_{start or 'all'}_to_{end or 'all'}.csv"
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(resp)
        writer.writerow(['Date', 'Patient', 'Doctor', 'Status', 'Medicines', 'Dispensed By', 'Dispensed At'])
        for p in qs:
            medicines = ', '.join([f"{m.drug_name} ({m.dosage})" for m in p.medicines.all()])
            writer.writerow([
                p.created_at.strftime('%Y-%m-%d %H:%M'),
                p.visit.patient.full_name if (p.visit and p.visit.patient) else 'Unknown',
                p.doctor.get_full_name() if p.doctor else 'Unknown',
                p.get_status_display(),
                medicines,
                p.dispensed_by.get_full_name() if p.dispensed_by else '',
                p.dispensed_at.strftime('%Y-%m-%d %H:%M') if p.dispensed_at else ''
            ])
        return resp
    
    if export == 'xlsx':
        try:
            from openpyxl import Workbook
            from django.http import HttpResponse
            wb = Workbook()
            ws = wb.active
            ws.title = 'Pharmacy Prescriptions'
            ws.append(['Date', 'Patient', 'Doctor', 'Status', 'Medicines', 'Dispensed By', 'Dispensed At'])
            for p in qs:
                medicines = ', '.join([f"{m.drug_name} ({m.dosage})" for m in p.medicines.all()])
                ws.append([
                    p.created_at.strftime('%Y-%m-%d %H:%M'),
                    p.visit.patient.full_name if (p.visit and p.visit.patient) else 'Unknown',
                    p.doctor.get_full_name() if p.doctor else 'Unknown',
                    p.get_status_display(),
                    medicines,
                    p.dispensed_by.get_full_name() if p.dispensed_by else '',
                    p.dispensed_at.strftime('%Y-%m-%d %H:%M') if p.dispensed_at else ''
                ])
            resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            filename = f"pharmacy_{start or 'all'}_to_{end or 'all'}.xlsx"
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            wb.save(resp)
            return resp
        except ImportError:
            messages.error(request, 'XLSX export is unavailable (openpyxl not installed).')
            return redirect('pharmacy_reports')
    
    if export == 'pdf':
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
            from django.http import HttpResponse
        except Exception:
            messages.error(request, 'PDF export is unavailable (reportlab not installed).')
            return redirect('pharmacy_reports')
        resp = HttpResponse(content_type='application/pdf')
        filename = f"pharmacy_{start or 'all'}_to_{end or 'all'}.pdf"
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        p = canvas.Canvas(resp, pagesize=landscape(A4))
        width, height = landscape(A4)
        y = height - 40
        p.setFont("Helvetica-Bold", 14)
        p.drawString(40, y, "Pharmacy Prescriptions Report")
        y -= 18
        p.setFont("Helvetica", 9)
        p.drawString(40, y, f"Date Range: {start or 'All'} to {end or 'All'}  |  Status: {status or 'All'}  |  Doctor: {doctor or 'All'}")
        y -= 20
        # Headers
        p.setFont("Helvetica-Bold", 10)
        p.drawString(40, y, "Date")
        p.drawString(140, y, "Patient")
        p.drawString(300, y, "Status")
        p.drawString(360, y, "Medicines")
        p.drawString(650, y, "Dispensed At")
        y -= 14
        p.setFont("Helvetica", 9)
        for rx in qs:
            if y < 40:
                p.showPage()
                width, height = landscape(A4)
                y = height - 40
                p.setFont("Helvetica-Bold", 10)
                p.drawString(40, y, "Date")
                p.drawString(140, y, "Patient")
                p.drawString(300, y, "Status")
                p.drawString(360, y, "Medicines")
                p.drawString(650, y, "Dispensed At")
                y -= 14
                p.setFont("Helvetica", 9)
            meds = ', '.join([f"{m.drug_name} ({m.dosage})" for m in rx.medicines.all()])[:1000]
            p.drawString(40, y, rx.created_at.strftime('%Y-%m-%d %H:%M'))
            p.drawString(140, y, (rx.visit.patient.full_name if (rx.visit and rx.visit.patient) else 'Unknown')[:24])
            p.drawString(300, y, rx.get_status_display())
            p.drawString(360, y, meds[:280])
            p.drawString(650, y, rx.dispensed_at.strftime('%Y-%m-%d %H:%M') if rx.dispensed_at else '-')
            y -= 12
        p.showPage()
        p.save()
        return resp
    
    # Statistics
    stats = {
        'total_prescriptions': qs.count(),
        'pending': qs.filter(status=Prescription.Status.PENDING).count(),
        'ready': qs.filter(status=Prescription.Status.READY).count(),
        'dispensed': qs.filter(status=Prescription.Status.DISPENSED).count(),
        'dispensed_today': qs.filter(
            status=Prescription.Status.DISPENSED,
            dispensed_at__date=timezone.localdate()
        ).count(),
    }
    
    # Get doctors for filter dropdown
    doctors = User.objects.filter(groups__name='Doctor').order_by('first_name', 'last_name')
    
    context = {
        'prescriptions': qs,
        'stats': stats,
        'doctors': doctors,
        'start': start or '',
        'end': end or '',
        'status': status or '',
        'doctor': doctor or '',
    }
    
    return render(request, 'dashboard/pharmacy_reports.html', context)


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
        'profile_photo_url': (p.profile_photo.url if p.profile_photo else ''),
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
                must_change_password=True  # Force password change on first login
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
        
        # Parse prescription medicines from form data
        medicines_data = []
        medicine_count = 0
        while True:
            drug_name = request.POST.get(f'medicine_{medicine_count}_name', '').strip()
            if not drug_name:
                break
            medicines_data.append({
                'drug_name': drug_name,
                'dosage': request.POST.get(f'medicine_{medicine_count}_dosage', '').strip(),
                'frequency': request.POST.get(f'medicine_{medicine_count}_frequency', '').strip(),
                'duration': request.POST.get(f'medicine_{medicine_count}_duration', '').strip(),
                'quantity': request.POST.get(f'medicine_{medicine_count}_quantity', '').strip(),
                'special_instructions': request.POST.get(f'medicine_{medicine_count}_instructions', '').strip(),
            })
            medicine_count += 1
        
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
            
            # Create detailed prescription if medicines are provided
            if medicines_data and done:
                from visits.models import Prescription, PrescriptionMedicine
                
                # Create or update prescription
                prescription, created = Prescription.objects.get_or_create(
                    visit=draft,
                    defaults={
                        'doctor': request.user,
                        'status': Prescription.Status.PENDING
                    }
                )
                
                # Clear existing medicines and add new ones
                prescription.medicines.all().delete()
                
                for medicine_data in medicines_data:
                    if medicine_data['drug_name']:  # Only create if drug name is provided
                        PrescriptionMedicine.objects.create(
                            prescription=prescription,
                            **medicine_data
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
    
    # Load existing prescription medicines if a draft exists
    prescription_medicines = []
    if draft and hasattr(draft, 'prescription_records') and draft.prescription_records.exists():
        prescription_medicines = draft.prescription_records.first().medicines.all()
    
    return render(request, 'dashboard/doctor_consult.html', {
        'rec': rec, 
        'draft': draft, 
        'prescription_medicines': prescription_medicines
    })


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
    # Load existing prescription medicines if they exist
    prescription_medicines = []
    if hasattr(visit, 'prescription_records') and visit.prescription_records.exists():
        prescription_medicines = visit.prescription_records.first().medicines.all()
    
    # Reuse consult template
    return render(request, 'dashboard/doctor_consult.html', {
        'rec': None, 
        'draft': visit, 
        'is_edit': True,
        'prescription_medicines': prescription_medicines
    })


@login_required
def change_password(request):
    """Allow any authenticated user to change their own password."""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password has been updated.')
            if request.user.is_superuser:
                return redirect('admin_dashboard')
            if request.user.groups.filter(name='Reception').exists():
                return redirect('dashboard_reception')
            if request.user.groups.filter(name='Doctor').exists():
                return redirect('dashboard_doctor')
            if request.user.groups.filter(name='Laboratory').exists():
                return redirect('dashboard_lab')
            if request.user.groups.filter(name='Pharmacy').exists():
                return redirect('dashboard_pharmacy')
            if request.user.groups.filter(name='Vaccination').exists():
                return redirect('dashboard_vaccination')
            return redirect('dashboard_index')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'dashboard/change_password.html', {'form': form})

