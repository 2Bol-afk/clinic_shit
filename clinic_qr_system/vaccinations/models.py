from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class VaccineType(models.Model):
    """Model for different types of vaccines with their dose requirements"""
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    total_doses_required = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Total number of doses required for complete vaccination"
    )
    dose_intervals = models.JSONField(
        default=list,
        help_text="List of intervals in days between doses (e.g., [0, 28, 180] for 0, 1 month, 6 months)"
    )
    age_minimum = models.PositiveIntegerField(
        default=0,
        help_text="Minimum age in months for this vaccine"
    )
    age_maximum = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum age in months for this vaccine (null for no limit)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def get_dose_schedule(self, start_date):
        """Calculate the schedule for all doses based on start date"""
        if not self.dose_intervals:
            return [start_date]
        
        schedule = []
        for interval in self.dose_intervals:
            schedule.append(start_date + timedelta(days=interval))
        return schedule


class PatientVaccination(models.Model):
    """Model for tracking patient vaccinations"""
    
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='vaccinations')
    vaccine_type = models.ForeignKey(VaccineType, on_delete=models.CASCADE, related_name='patient_vaccinations')
    started_date = models.DateField(default=timezone.now)
    completed = models.BooleanField(default=False)
    completion_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['patient', 'vaccine_type']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.vaccine_type.name}"
    
    def get_next_dose_number(self):
        """Get the next dose number that needs to be administered"""
        administered_doses = self.doses.filter(administered=True).count()
        return administered_doses + 1
    
    def get_next_dose_date(self):
        """Get the scheduled date for the next dose"""
        next_dose_number = self.get_next_dose_number()
        if next_dose_number > self.vaccine_type.total_doses_required:
            return None
        
        schedule = self.vaccine_type.get_dose_schedule(self.started_date)
        if next_dose_number <= len(schedule):
            return schedule[next_dose_number - 1]
        return None
    
    def is_overdue(self):
        """Check if the next dose is overdue"""
        next_date = self.get_next_dose_date()
        if next_date and next_date < timezone.now().date():
            return True
        return False
    
    def get_completion_percentage(self):
        """Get the percentage of doses completed"""
        administered = self.doses.filter(administered=True).count()
        return (administered / self.vaccine_type.total_doses_required) * 100

    def administered_count(self):
        """Return the number of doses that have been administered."""
        return self.doses.filter(administered=True).count()

    def last_administered_date(self):
        """Return the date of the last administered dose, or None if none."""
        last_admin = self.doses.filter(administered=True).order_by('-administered_date').first()
        return last_admin.administered_date if last_admin else None


class VaccineDose(models.Model):
    """Model for individual vaccine doses"""
    
    vaccination = models.ForeignKey(PatientVaccination, on_delete=models.CASCADE, related_name='doses')
    dose_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Dose number (1st, 2nd, 3rd, etc.)"
    )
    scheduled_date = models.DateField()
    administered_date = models.DateField(null=True, blank=True)
    administered = models.BooleanField(default=False)
    administered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='administered_doses')
    batch_number = models.CharField(max_length=50, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    site_of_injection = models.CharField(max_length=100, blank=True, help_text="e.g., Left arm, Right arm")
    adverse_reactions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['vaccination', 'dose_number']
        ordering = ['dose_number']
    
    def __str__(self):
        return f"{self.vaccination} - Dose {self.dose_number}"
    
    def is_overdue(self):
        """Check if this dose is overdue"""
        return self.scheduled_date < timezone.now().date() and not self.administered
    
    def can_be_administered(self):
        """Check if this dose can be administered"""
        return not self.administered and self.scheduled_date <= timezone.now().date()


class VaccinationReminder(models.Model):
    """Model for tracking vaccination reminders"""
    
    dose = models.ForeignKey(VaccineDose, on_delete=models.CASCADE, related_name='reminders')
    reminder_date = models.DateField()
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['reminder_date']
    
    def __str__(self):
        return f"Reminder for {self.dose} - {self.reminder_date}"
