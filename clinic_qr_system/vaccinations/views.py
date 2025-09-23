from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
from .models import VaccineType, PatientVaccination, VaccineDose, VaccinationReminder
from .forms import (
    VaccineTypeForm, PatientVaccinationForm, VaccineDoseForm, 
    VaccinationScheduleForm, VaccinationReminderForm, BulkVaccinationForm,
    DynamicVaccinationForm
)
from clinic_qr_system.email_utils import send_notification_email
import json


@login_required
def vaccine_type_list(request):
    """List all vaccine types"""
    vaccine_types = VaccineType.objects.all().order_by('name')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        vaccine_types = vaccine_types.filter(
            Q(name__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    # Filter by active status
    active_filter = request.GET.get('active', '')
    if active_filter == 'true':
        vaccine_types = vaccine_types.filter(is_active=True)
    elif active_filter == 'false':
        vaccine_types = vaccine_types.filter(is_active=False)
    
    paginator = Paginator(vaccine_types, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'active_filter': active_filter,
    }
    return render(request, 'vaccinations/vaccine_type_list.html', context)


@login_required
def vaccine_type_create(request):
    """Create a new vaccine type"""
    if request.method == 'POST':
        form = VaccineTypeForm(request.POST)
        if form.is_valid():
            vaccine_type = form.save()
            messages.success(request, f'Vaccine type "{vaccine_type.name}" created successfully.')
            return redirect('vaccinations:vaccine_type_list')
    else:
        form = VaccineTypeForm()
    
    return render(request, 'vaccinations/vaccine_type_form.html', {'form': form, 'title': 'Create Vaccine Type'})


@login_required
def vaccine_type_edit(request, pk):
    """Edit a vaccine type"""
    vaccine_type = get_object_or_404(VaccineType, pk=pk)
    
    if request.method == 'POST':
        form = VaccineTypeForm(request.POST, instance=vaccine_type)
        if form.is_valid():
            vaccine_type = form.save()
            messages.success(request, f'Vaccine type "{vaccine_type.name}" updated successfully.')
            return redirect('vaccinations:vaccine_type_list')
    else:
        form = VaccineTypeForm(instance=vaccine_type)
    
    return render(request, 'vaccinations/vaccine_type_form.html', {
        'form': form, 
        'title': f'Edit {vaccine_type.name}',
        'vaccine_type': vaccine_type
    })


@login_required
def dynamic_vaccination_form(request):
    """Dynamic vaccination form with dose selection and duplicate prevention"""
    if request.method == 'POST':
        form = DynamicVaccinationForm(request.POST)
        if form.is_valid():
            patient = form.cleaned_data['patient']
            vaccine_type = form.cleaned_data['vaccine_type']
            dose_number = int(form.cleaned_data['dose_number'])
            administered_date = form.cleaned_data['administered_date']
            
            # Get or create vaccination record
            vaccination, created = PatientVaccination.objects.get_or_create(
                patient=patient,
                vaccine_type=vaccine_type,
                defaults={
                    'started_date': administered_date,
                    'created_by': request.user
                }
            )
            
            # Create or update dose record
            dose, dose_created = VaccineDose.objects.get_or_create(
                vaccination=vaccination,
                dose_number=dose_number,
                defaults={
                    'scheduled_date': administered_date,
                    'administered_date': administered_date,
                    'administered': True,
                    'administered_by': request.user,
                    'batch_number': form.cleaned_data.get('batch_number', ''),
                    'expiry_date': form.cleaned_data.get('expiry_date'),
                    'site_of_injection': form.cleaned_data.get('site_of_injection', ''),
                    'adverse_reactions': form.cleaned_data.get('adverse_reactions', ''),
                    'notes': form.cleaned_data.get('notes', ''),
                }
            )
            
            if not dose_created:
                # Update existing dose
                dose.administered_date = administered_date
                dose.administered = True
                dose.administered_by = request.user
                dose.batch_number = form.cleaned_data.get('batch_number', '')
                dose.expiry_date = form.cleaned_data.get('expiry_date')
                dose.site_of_injection = form.cleaned_data.get('site_of_injection', '')
                dose.adverse_reactions = form.cleaned_data.get('adverse_reactions', '')
                dose.notes = form.cleaned_data.get('notes', '')
                dose.save()
            
            # Check if vaccination is complete
            total_doses = vaccination.vaccine_type.total_doses_required
            administered_doses = vaccination.doses.filter(administered=True).count()
            
            if administered_doses >= total_doses:
                vaccination.completed = True
                vaccination.completion_date = administered_date
                vaccination.save()
                
                # Send completion email
                send_vaccination_completion_email(vaccination)
                messages.success(request, f'Dose {dose_number} of {vaccine_type.name} administered to {patient.full_name}. Vaccination series completed!')
            else:
                # Schedule next dose if applicable
                next_dose_number = dose_number + 1
                if next_dose_number <= total_doses:
                    schedule = vaccine_type.get_dose_schedule(vaccination.started_date)
                    if next_dose_number <= len(schedule):
                        next_dose_date = schedule[next_dose_number - 1]
                        VaccineDose.objects.get_or_create(
                            vaccination=vaccination,
                            dose_number=next_dose_number,
                            defaults={'scheduled_date': next_dose_date}
                        )
                
                messages.success(request, f'Dose {dose_number} of {vaccine_type.name} administered to {patient.full_name} successfully.')
            
            return redirect('vaccinations:patient_vaccination_detail', pk=vaccination.pk)
    else:
        form = DynamicVaccinationForm()
    
    return render(request, 'vaccinations/dynamic_vaccination_form.html', {'form': form})


@login_required
def vaccination_schedule(request):
    """Schedule vaccinations for patients"""
    if request.method == 'POST':
        form = VaccinationScheduleForm(request.POST)
        if form.is_valid():
            patient = form.cleaned_data['patient']
            vaccine_type = form.cleaned_data['vaccine_type']
            start_date = form.cleaned_data['start_date']
            
            # Check if patient already has this vaccination
            existing_vaccination = PatientVaccination.objects.filter(
                patient=patient, vaccine_type=vaccine_type
            ).first()
            
            if existing_vaccination:
                messages.warning(request, f'{patient.full_name} already has a {vaccine_type.name} vaccination record.')
            else:
                # Create vaccination record
                vaccination = PatientVaccination.objects.create(
                    patient=patient,
                    vaccine_type=vaccine_type,
                    started_date=start_date,
                    created_by=request.user
                )
                
                # Create dose records based on schedule
                schedule = vaccine_type.get_dose_schedule(start_date)
                for i, dose_date in enumerate(schedule, 1):
                    VaccineDose.objects.create(
                        vaccination=vaccination,
                        dose_number=i,
                        scheduled_date=dose_date
                    )
                
                messages.success(request, f'Vaccination scheduled for {patient.full_name}.')
                return redirect('vaccinations:patient_vaccination_detail', pk=vaccination.pk)
    else:
        form = VaccinationScheduleForm()
    
    return render(request, 'vaccinations/vaccination_schedule.html', {'form': form})


@login_required
def patient_vaccination_list(request):
    """List all patient vaccinations"""
    vaccinations = PatientVaccination.objects.select_related(
        'patient', 'vaccine_type', 'created_by'
    ).order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        vaccinations = vaccinations.filter(
            Q(patient__full_name__icontains=search_query) |
            Q(patient__patient_code__icontains=search_query) |
            Q(vaccine_type__name__icontains=search_query)
        )
    
    # Filter by completion status
    status_filter = request.GET.get('status', '')
    if status_filter == 'completed':
        vaccinations = vaccinations.filter(completed=True)
    elif status_filter == 'pending':
        vaccinations = vaccinations.filter(completed=False)
    
    # Filter by overdue
    overdue_filter = request.GET.get('overdue', '')
    if overdue_filter == 'true':
        vaccinations = vaccinations.filter(completed=False)
        # Filter for overdue vaccinations
        overdue_vaccinations = []
        for vaccination in vaccinations:
            if vaccination.is_overdue():
                overdue_vaccinations.append(vaccination.pk)
        vaccinations = vaccinations.filter(pk__in=overdue_vaccinations)
    
    paginator = Paginator(vaccinations, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'overdue_filter': overdue_filter,
    }
    return render(request, 'vaccinations/patient_vaccination_list.html', context)


@login_required
def patient_vaccination_detail(request, pk):
    """View detailed information about a patient vaccination"""
    vaccination = get_object_or_404(PatientVaccination, pk=pk)
    doses = vaccination.doses.all().order_by('dose_number')
    
    context = {
        'vaccination': vaccination,
        'doses': doses,
    }
    return render(request, 'vaccinations/patient_vaccination_detail.html', context)


@login_required
def patient_vaccination_timeline(request, patient_id):
    """View vaccination timeline for a specific patient"""
    from patients.models import Patient
    patient = get_object_or_404(Patient, pk=patient_id)
    
    # Get all vaccinations for this patient
    vaccinations = PatientVaccination.objects.filter(
        patient=patient
    ).select_related('vaccine_type', 'created_by').prefetch_related('doses').order_by('-started_date')
    
    # Calculate summary statistics
    completed_count = vaccinations.filter(completed=True).count()
    in_progress_count = vaccinations.filter(completed=False).count()
    overdue_count = sum(1 for v in vaccinations if v.is_overdue())
    
    # Get overdue vaccinations
    overdue_vaccinations = [v for v in vaccinations if v.is_overdue()]
    
    context = {
        'patient': patient,
        'vaccinations': vaccinations,
        'completed_count': completed_count,
        'in_progress_count': in_progress_count,
        'overdue_count': overdue_count,
        'overdue_vaccinations': overdue_vaccinations,
    }
    return render(request, 'vaccinations/vaccination_timeline.html', context)


@login_required
def administer_dose(request, pk):
    """Administer a vaccine dose"""
    dose = get_object_or_404(VaccineDose, pk=pk)
    
    if request.method == 'POST':
        form = VaccineDoseForm(request.POST, instance=dose)
        if form.is_valid():
            dose = form.save(commit=False)
            dose.administered = True
            dose.administered_by = request.user
            if not dose.administered_date:
                dose.administered_date = timezone.now().date()
            dose.save()
            
            # Check if vaccination is complete
            vaccination = dose.vaccination
            total_doses = vaccination.vaccine_type.total_doses_required
            administered_doses = vaccination.doses.filter(administered=True).count()
            
            if administered_doses >= total_doses:
                vaccination.completed = True
                vaccination.completion_date = dose.administered_date
                vaccination.save()
                
                # Send completion email
                send_vaccination_completion_email(vaccination)
                messages.success(request, f'Dose {dose.dose_number} administered and vaccination completed!')
            else:
                messages.success(request, f'Dose {dose.dose_number} administered successfully.')
            
            return redirect('vaccinations:patient_vaccination_detail', pk=vaccination.pk)
    else:
        form = VaccineDoseForm(instance=dose)
    
    context = {
        'dose': dose,
        'form': form,
    }
    return render(request, 'vaccinations/administer_dose.html', context)


@login_required
def vaccination_dashboard(request):
    """Dashboard showing vaccination statistics and upcoming doses"""
    # Statistics
    total_vaccinations = PatientVaccination.objects.count()
    completed_vaccinations = PatientVaccination.objects.filter(completed=True).count()
    pending_vaccinations = PatientVaccination.objects.filter(completed=False).count()
    
    # Upcoming doses (next 7 days)
    upcoming_doses = VaccineDose.objects.filter(
        administered=False,
        scheduled_date__lte=timezone.now().date() + timedelta(days=7),
        scheduled_date__gte=timezone.now().date()
    ).select_related('vaccination__patient', 'vaccination__vaccine_type').order_by('scheduled_date')
    
    # Overdue doses
    overdue_doses = VaccineDose.objects.filter(
        administered=False,
        scheduled_date__lt=timezone.now().date()
    ).select_related('vaccination__patient', 'vaccination__vaccine_type').order_by('scheduled_date')
    
    # Vaccine type statistics
    vaccine_stats = VaccineType.objects.annotate(
        total_patients=Count('patient_vaccinations'),
        completed_patients=Count('patient_vaccinations', filter=Q(patient_vaccinations__completed=True))
    ).order_by('-total_patients')
    
    context = {
        'total_vaccinations': total_vaccinations,
        'completed_vaccinations': completed_vaccinations,
        'pending_vaccinations': pending_vaccinations,
        'upcoming_doses': upcoming_doses,
        'overdue_doses': overdue_doses,
        'vaccine_stats': vaccine_stats,
    }
    return render(request, 'vaccinations/dashboard.html', context)


@login_required
def send_reminders(request):
    """Send vaccination reminders"""
    if request.method == 'POST':
        # Get doses that need reminders
        tomorrow = timezone.now().date() + timedelta(days=1)
        doses_needing_reminders = VaccineDose.objects.filter(
            administered=False,
            scheduled_date=tomorrow
        ).select_related('vaccination__patient', 'vaccination__vaccine_type')
        
        sent_count = 0
        for dose in doses_needing_reminders:
            if send_vaccination_reminder_email(dose):
                sent_count += 1
        
        messages.success(request, f'Reminders sent to {sent_count} patients.')
        return redirect('vaccinations:dashboard')
    
    return render(request, 'vaccinations/send_reminders.html')


@login_required
def bulk_vaccination(request):
    """Bulk vaccination operations"""
    if request.method == 'POST':
        form = BulkVaccinationForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            patients = form.cleaned_data['patients']
            vaccine_type = form.cleaned_data['vaccine_type']
            start_date = form.cleaned_data['start_date']
            
            if action == 'schedule':
                scheduled_count = 0
                for patient in patients:
                    if not PatientVaccination.objects.filter(patient=patient, vaccine_type=vaccine_type).exists():
                        vaccination = PatientVaccination.objects.create(
                            patient=patient,
                            vaccine_type=vaccine_type,
                            started_date=start_date,
                            created_by=request.user
                        )
                        
                        # Create dose records
                        schedule = vaccine_type.get_dose_schedule(start_date)
                        for i, dose_date in enumerate(schedule, 1):
                            VaccineDose.objects.create(
                                vaccination=vaccination,
                                dose_number=i,
                                scheduled_date=dose_date
                            )
                        scheduled_count += 1
                
                messages.success(request, f'Vaccinations scheduled for {scheduled_count} patients.')
            
            elif action == 'send_reminders':
                sent_count = 0
                for patient in patients:
                    vaccinations = PatientVaccination.objects.filter(
                        patient=patient, 
                        vaccine_type=vaccine_type,
                        completed=False
                    )
                    for vaccination in vaccinations:
                        next_dose = vaccination.doses.filter(administered=False).first()
                        if next_dose and next_dose.scheduled_date <= timezone.now().date() + timedelta(days=1):
                            if send_vaccination_reminder_email(next_dose):
                                sent_count += 1
                
                messages.success(request, f'Reminders sent to {sent_count} patients.')
            
            return redirect('vaccinations:dashboard')
    else:
        form = BulkVaccinationForm()
    
    return render(request, 'vaccinations/bulk_vaccination.html', {'form': form})


def send_vaccination_reminder_email(dose):
    """Send vaccination reminder email"""
    try:
        patient = dose.vaccination.patient
        vaccine_name = dose.vaccination.vaccine_type.name
        
        # Create dose ordinal (1st, 2nd, 3rd, etc.)
        dose_ordinal = get_dose_ordinal(dose.dose_number)
        
        subject = f"Reminder: Your {dose_ordinal} dose of {vaccine_name} vaccine is due today"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c5aa0; border-bottom: 2px solid #2c5aa0; padding-bottom: 10px;">
                    Vaccination Reminder
                </h2>
                
                <p>Hello <strong>{patient.full_name}</strong>,</p>
                
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <h3 style="color: #856404; margin-top: 0;">
                        <i class="bi bi-calendar-event" style="margin-right: 8px;"></i>
                        Your {dose_ordinal} dose of {vaccine_name} vaccine is due today
                    </h3>
                    <p style="margin-bottom: 0; color: #856404;">
                        Please visit the vaccination center to complete your schedule.
                    </p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4 style="color: #2c5aa0; margin-top: 0;">Vaccination Details</h4>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 5px 0; font-weight: bold; width: 120px;">Vaccine:</td>
                            <td style="padding: 5px 0;">{vaccine_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; font-weight: bold;">Dose:</td>
                            <td style="padding: 5px 0;">{dose_ordinal} Dose</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; font-weight: bold;">Due Date:</td>
                            <td style="padding: 5px 0;">{dose.scheduled_date}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; font-weight: bold;">Patient Code:</td>
                            <td style="padding: 5px 0;">{patient.patient_code}</td>
                        </tr>
                    </table>
                </div>
                
                <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4 style="color: #2c5aa0; margin-top: 0;">Important Instructions</h4>
                    <ul style="margin-bottom: 0;">
                        <li>Please arrive on time for your vaccination appointment</li>
                        <li>Bring your patient ID and any relevant medical documents</li>
                        <li>Inform the staff if you have any allergies or medical conditions</li>
                        <li>Stay hydrated and have a light meal before your appointment</li>
                    </ul>
                </div>
                
                <p>If you need to reschedule or have any questions, please contact us immediately.</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    Regards,<br>
                    Clinic QR System<br>
                    Vaccination Department
                </p>
            </div>
        </body>
        </html>
        """
        
        plain_message = f"""
Hello {patient.full_name}, your scheduled {dose_ordinal} dose of {vaccine_name} vaccine is due today. Please visit the vaccination center to complete your schedule.

Vaccination Details:
- Vaccine: {vaccine_name}
- Dose: {dose_ordinal} Dose
- Due Date: {dose.scheduled_date}
- Patient Code: {patient.patient_code}

Important Instructions:
- Please arrive on time for your vaccination appointment
- Bring your patient ID and any relevant medical documents
- Inform the staff if you have any allergies or medical conditions
- Stay hydrated and have a light meal before your appointment

If you need to reschedule or have any questions, please contact us immediately.

Regards,
Clinic QR System
Vaccination Department
        """.strip()
        
        result = send_notification_email(
            recipient_list=[patient.email],
            subject=subject,
            message=plain_message,
            html_message=html_message
        )
        
        if result:
            # Create reminder record
            VaccinationReminder.objects.create(
                dose=dose,
                reminder_date=timezone.now().date(),
                sent=True,
                sent_at=timezone.now(),
                email_sent=True
            )
        
        return result
        
    except Exception as e:
        print(f"Failed to send vaccination reminder email: {e}")
        return False


def get_dose_ordinal(dose_number):
    """Convert dose number to ordinal (1st, 2nd, 3rd, etc.)"""
    if dose_number == 1:
        return "1st"
    elif dose_number == 2:
        return "2nd"
    elif dose_number == 3:
        return "3rd"
    else:
        return f"{dose_number}th"


def send_vaccination_completion_email(vaccination):
    """Send vaccination completion email"""
    try:
        patient = vaccination.patient
        vaccine_name = vaccination.vaccine_type.name
        
        subject = f"Vaccination Complete - {vaccine_name}"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 10px;">
                    Vaccination Complete! 🎉
                </h2>
                
                <p>Dear <strong>{patient.full_name}</strong>,</p>
                
                <div style="background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #28a745;">
                    <h3 style="color: #155724; margin-top: 0;">Congratulations!</h3>
                    <p>You have successfully completed your <strong>{vaccine_name}</strong> vaccination series.</p>
                    <p><strong>Completion Date:</strong> {vaccination.completion_date}</p>
                </div>
                
                <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4 style="color: #2c5aa0; margin-top: 0;">Important Information</h4>
                    <ul>
                        <li>Keep your vaccination record safe for future reference</li>
                        <li>Monitor for any side effects and contact us if needed</li>
                        <li>Follow any post-vaccination care instructions provided</li>
                        <li>Your vaccination record is now part of your medical history</li>
                    </ul>
                </div>
                
                <p>Thank you for completing your vaccination series. Stay healthy!</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    Regards,<br>
                    Clinic QR System<br>
                    Vaccination Department
                </p>
            </div>
        </body>
        </html>
        """
        
        plain_message = f"""
Dear {patient.full_name},

Congratulations! You have successfully completed your {vaccine_name} vaccination series.

Completion Date: {vaccination.completion_date}

Important Information:
- Keep your vaccination record safe for future reference
- Monitor for any side effects and contact us if needed
- Follow any post-vaccination care instructions provided
- Your vaccination record is now part of your medical history

Thank you for completing your vaccination series. Stay healthy!

Regards,
Clinic QR System
Vaccination Department
        """.strip()
        
        return send_notification_email(
            recipient_list=[patient.email],
            subject=subject,
            message=plain_message,
            html_message=html_message
        )
        
    except Exception as e:
        print(f"Failed to send vaccination completion email: {e}")
        return False


# AJAX views for dynamic forms
@login_required
def get_vaccine_info(request):
    """Get vaccine information for AJAX requests"""
    vaccine_id = request.GET.get('vaccine_id')
    patient_id = request.GET.get('patient_id')
    
    if vaccine_id:
        try:
            vaccine = VaccineType.objects.get(pk=vaccine_id)
            
            # Get available dose numbers for this patient and vaccine
            available_doses = []
            if patient_id:
                try:
                    from patients.models import Patient
                    patient = Patient.objects.get(pk=patient_id)
                    
                    # Check if patient has existing vaccination
                    existing_vaccination = PatientVaccination.objects.filter(
                        patient=patient, vaccine_type=vaccine
                    ).first()
                    
                    if existing_vaccination:
                        # Get administered doses
                        administered_doses = existing_vaccination.doses.filter(
                            administered=True
                        ).values_list('dose_number', flat=True)
                        
                        # Available doses are those not yet administered
                        for dose_num in range(1, vaccine.total_doses_required + 1):
                            if dose_num not in administered_doses:
                                available_doses.append(dose_num)
                    else:
                        # New vaccination - only first dose available
                        available_doses = [1]
                        
                except Patient.DoesNotExist:
                    pass
            
            # If no patient selected, show all possible doses
            if not available_doses:
                available_doses = list(range(1, vaccine.total_doses_required + 1))
            
            return JsonResponse({
                'success': True,
                'total_doses': vaccine.total_doses_required,
                'available_doses': available_doses,
                'description': vaccine.description
            })
        except VaccineType.DoesNotExist:
            pass
    
    return JsonResponse({'success': False})


@login_required
def get_vaccine_schedule(request):
    """Get vaccine schedule for AJAX requests"""
    vaccine_id = request.GET.get('vaccine_id')
    start_date = request.GET.get('start_date')
    
    if vaccine_id and start_date:
        try:
            vaccine = VaccineType.objects.get(pk=vaccine_id)
            schedule = vaccine.get_dose_schedule(start_date)
            
            return JsonResponse({
                'success': True,
                'schedule': [date.strftime('%Y-%m-%d') for date in schedule],
                'total_doses': vaccine.total_doses_required
            })
        except (VaccineType.DoesNotExist, ValueError):
            pass
    
    return JsonResponse({'success': False})


@login_required
def search_patients(request):
    """Search patients for AJAX requests"""
    query = request.GET.get('q', '')
    if len(query) >= 2:
        from patients.models import Patient
        patients = Patient.objects.filter(
            Q(full_name__icontains=query) | Q(patient_code__icontains=query)
        )[:10]
        
        results = [{
            'id': patient.id,
            'name': patient.full_name,
            'code': patient.patient_code,
            'email': patient.email
        } for patient in patients]
        
        return JsonResponse({'results': results})
    
    return JsonResponse({'results': []})
