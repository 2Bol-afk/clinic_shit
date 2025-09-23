from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import VaccineType, PatientVaccination, VaccineDose, VaccinationReminder


class VaccineTypeForm(forms.ModelForm):
    """Form for creating and editing vaccine types"""
    
    class Meta:
        model = VaccineType
        fields = [
            'name', 'description', 'total_doses_required', 
            'dose_intervals', 'age_minimum', 'age_maximum', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'total_doses_required': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'age_minimum': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'age_maximum': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_dose_intervals(self):
        """Validate dose intervals"""
        intervals = self.cleaned_data.get('dose_intervals')
        if not intervals:
            return [0]  # Default to single dose
        
        # Ensure intervals are non-negative and sorted
        intervals = sorted([max(0, int(interval)) for interval in intervals])
        
        # Ensure first interval is 0 (immediate first dose)
        if intervals[0] != 0:
            intervals.insert(0, 0)
        
        return intervals
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        total_doses = cleaned_data.get('total_doses_required')
        intervals = cleaned_data.get('dose_intervals')
        
        if total_doses and intervals and len(intervals) != total_doses:
            raise ValidationError(
                f"Number of dose intervals ({len(intervals)}) must match total doses required ({total_doses})"
            )
        
        return cleaned_data


class DynamicVaccinationForm(forms.Form):
    """Dynamic vaccination form with dose selection and duplicate prevention"""
    
    patient = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'patient-select'}),
        empty_label="Select a patient",
        help_text="Choose the patient to vaccinate"
    )
    
    vaccine_type = forms.ModelChoiceField(
        queryset=VaccineType.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'vaccine-type-select'}),
        empty_label="Select a vaccine type",
        help_text="Choose the vaccine to administer"
    )
    
    dose_number = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'dose-number-select'}),
        help_text="Select the dose number to administer"
    )
    
    administered_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'id': 'administered-date',
            'value': timezone.now().date().strftime('%Y-%m-%d')
        }),
        initial=timezone.now().date(),
        help_text="Date when the vaccine was administered"
    )
    
    batch_number = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter batch number'}),
        help_text="Vaccine batch number (optional)"
    )
    
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Vaccine expiry date (optional)"
    )
    
    site_of_injection = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Left arm, Right arm'}),
        help_text="Site of injection (optional)"
    )
    
    adverse_reactions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Any adverse reactions observed'}),
        help_text="Record any adverse reactions (optional)"
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes'}),
        help_text="Additional notes (optional)"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from patients.models import Patient
        self.fields['patient'].queryset = Patient.objects.all().order_by('full_name')
    
    def clean_administered_date(self):
        """Validate administered date"""
        administered_date = self.cleaned_data.get('administered_date')
        if administered_date and administered_date > timezone.now().date():
            raise ValidationError("Administered date cannot be in the future")
        return administered_date
    
    def clean_expiry_date(self):
        """Validate expiry date"""
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date and expiry_date <= timezone.now().date():
            raise ValidationError("Expiry date must be in the future")
        return expiry_date
    
    def clean(self):
        """Cross-field validation for duplicate prevention"""
        cleaned_data = super().clean()
        patient = cleaned_data.get('patient')
        vaccine_type = cleaned_data.get('vaccine_type')
        dose_number = cleaned_data.get('dose_number')
        
        if patient and vaccine_type and dose_number:
            # Check for duplicate vaccination record
            try:
                vaccination = PatientVaccination.objects.get(
                    patient=patient,
                    vaccine_type=vaccine_type
                )
                
                # Check if this dose number already exists
                existing_dose = vaccination.doses.filter(dose_number=int(dose_number)).first()
                if existing_dose and existing_dose.administered:
                    raise ValidationError(
                        f"Dose {dose_number} of {vaccine_type.name} has already been administered to {patient.full_name} on {existing_dose.administered_date}"
                    )
                
                # Check if dose number is valid for this vaccine
                if int(dose_number) > vaccine_type.total_doses_required:
                    raise ValidationError(
                        f"Invalid dose number. {vaccine_type.name} only requires {vaccine_type.total_doses_required} doses."
                    )
                
            except PatientVaccination.DoesNotExist:
                # This is a new vaccination series
                if int(dose_number) != 1:
                    raise ValidationError(
                        f"First dose must be dose number 1 for a new vaccination series."
                    )
        
        return cleaned_data


class PatientVaccinationForm(forms.ModelForm):
    """Form for creating patient vaccination records"""
    
    patient_search = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by patient name or code...',
            'id': 'patient-search'
        }),
        help_text="Start typing to search for a patient"
    )
    
    class Meta:
        model = PatientVaccination
        fields = ['vaccine_type', 'started_date', 'notes']
        widgets = {
            'vaccine_type': forms.Select(attrs={'class': 'form-control'}),
            'started_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'max': timezone.now().date().strftime('%Y-%m-%d')
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active vaccine types
        self.fields['vaccine_type'].queryset = VaccineType.objects.filter(is_active=True)
        self.fields['vaccine_type'].empty_label = "Select a vaccine type"
    
    def clean_started_date(self):
        """Validate started date"""
        started_date = self.cleaned_data.get('started_date')
        if started_date and started_date > timezone.now().date():
            raise ValidationError("Start date cannot be in the future")
        return started_date


class VaccineDoseForm(forms.ModelForm):
    """Form for administering vaccine doses"""
    
    class Meta:
        model = VaccineDose
        fields = [
            'administered_date', 'batch_number', 'expiry_date', 
            'site_of_injection', 'adverse_reactions', 'notes'
        ]
        widgets = {
            'administered_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'max': timezone.now().date().strftime('%Y-%m-%d')
            }),
            'batch_number': forms.TextInput(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'site_of_injection': forms.TextInput(attrs={'class': 'form-control'}),
            'adverse_reactions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def clean_administered_date(self):
        """Validate administered date"""
        administered_date = self.cleaned_data.get('administered_date')
        if administered_date and administered_date > timezone.now().date():
            raise ValidationError("Administered date cannot be in the future")
        return administered_date
    
    def clean_expiry_date(self):
        """Validate expiry date"""
        expiry_date = self.cleaned_data.get('expiry_date')
        if expiry_date and expiry_date <= timezone.now().date():
            raise ValidationError("Expiry date must be in the future")
        return expiry_date


class VaccinationScheduleForm(forms.Form):
    """Form for scheduling vaccination doses"""
    
    patient = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select a patient"
    )
    vaccine_type = forms.ModelChoiceField(
        queryset=VaccineType.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select a vaccine type"
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'max': timezone.now().date().strftime('%Y-%m-%d')
        }),
        help_text="Date when the first dose will be administered"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set queryset for patients
        from patients.models import Patient
        self.fields['patient'].queryset = Patient.objects.all().order_by('full_name')
    
    def clean_start_date(self):
        """Validate start date"""
        start_date = self.cleaned_data.get('start_date')
        if start_date and start_date > timezone.now().date():
            raise ValidationError("Start date cannot be in the future")
        return start_date


class VaccinationReminderForm(forms.ModelForm):
    """Form for creating vaccination reminders"""
    
    class Meta:
        model = VaccinationReminder
        fields = ['reminder_date']
        widgets = {
            'reminder_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'min': timezone.now().date().strftime('%Y-%m-%d')
            }),
        }
    
    def clean_reminder_date(self):
        """Validate reminder date"""
        reminder_date = self.cleaned_data.get('reminder_date')
        if reminder_date and reminder_date < timezone.now().date():
            raise ValidationError("Reminder date cannot be in the past")
        return reminder_date


class BulkVaccinationForm(forms.Form):
    """Form for bulk vaccination operations"""
    
    ACTION_CHOICES = [
        ('schedule', 'Schedule Vaccinations'),
        ('send_reminders', 'Send Reminders'),
        ('mark_complete', 'Mark as Complete'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    vaccine_type = forms.ModelChoiceField(
        queryset=VaccineType.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select a vaccine type",
        required=False
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'max': timezone.now().date().strftime('%Y-%m-%d')
        }),
        required=False,
        help_text="Start date for scheduling (required for scheduling action)"
    )
    patients = forms.ModelMultipleChoiceField(
        queryset=None,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from patients.models import Patient
        self.fields['patients'].queryset = Patient.objects.all().order_by('full_name')
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        start_date = cleaned_data.get('start_date')
        patients = cleaned_data.get('patients')
        
        if action == 'schedule' and not start_date:
            raise ValidationError("Start date is required for scheduling vaccinations")
        
        if action in ['schedule', 'send_reminders', 'mark_complete'] and not patients:
            raise ValidationError("Please select at least one patient")
        
        return cleaned_data
