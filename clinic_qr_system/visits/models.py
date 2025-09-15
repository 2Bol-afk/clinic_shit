from django.db import models
from django.conf import settings


class Visit(models.Model):
    class Service(models.TextChoices):
        RECEPTION = 'reception', 'Reception/Triage'
        DOCTOR = 'doctor', 'Doctor Consultation'
        LAB = 'lab', 'Laboratory'
        PHARMACY = 'pharmacy', 'Pharmacy'
        VACCINATION = 'vaccination', 'Vaccination/Immunization'

    class Department(models.TextChoices):
        GENERAL = 'General Medicine', 'General Medicine'
        PEDIATRICS = 'Pediatrics', 'Pediatrics'
        OBGYN = 'OB-GYN', 'OB-GYN'
        OTHERS = 'Others', 'Others'

    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='visits')
    service = models.CharField(max_length=20, choices=Service.choices)
    notes = models.TextField(blank=True)
    # Reception
    queue_number = models.PositiveIntegerField(null=True, blank=True)
    department = models.CharField(max_length=32, choices=Department.choices, blank=True)
    claimed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='claimed_reception_visits')
    claimed_at = models.DateTimeField(null=True, blank=True)
    # Doctor
    symptoms = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    prescription_notes = models.TextField(blank=True)
    doctor_done = models.BooleanField(default=False)
    doctor_done_at = models.DateTimeField(null=True, blank=True)
    # Lab
    lab_tests = models.TextField(blank=True)
    lab_completed = models.BooleanField(default=False)
    lab_completed_at = models.DateTimeField(null=True, blank=True)
    # Pharmacy
    medicines = models.TextField(blank=True)
    dispensed = models.BooleanField(default=False)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    # Vaccination
    vaccine_type = models.CharField(max_length=100, blank=True)
    vaccine_dose = models.CharField(max_length=50, blank=True)
    vaccination_date = models.DateField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    doctor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='doctor_visits')

    def __str__(self) -> str:
        return f"{self.patient} - {self.get_service_display()} @ {self.timestamp:%Y-%m-%d %H:%M}"

# Create your models here.
