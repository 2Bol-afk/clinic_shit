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
        PEDIATRICS = 'Pediatrics', 'Pediatrics (Children’s Health)'
        OBGYN = 'OB-GYN', 'Obstetrics and Gynecology (OB-GYN)'
        CARDIOLOGY = 'Cardiology', 'Cardiology (Heart Care)'
        RADIOLOGY = 'Radiology', 'Radiology'
        SURGERY = 'Surgery', 'Surgery'
        DERMATOLOGY = 'Dermatology', 'Dermatology (Skin Care)'
        ENT = 'ENT', 'ENT (Ear, Nose, Throat)'

    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='visits')
    service = models.CharField(max_length=20, choices=Service.choices)
    notes = models.TextField(blank=True)
    # Unified workflow status across services (4 states)
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        CLAIMED = 'claimed', 'Claimed'
        IN_PROCESS = 'in_process', 'In Process'
        DONE = 'done', 'Done'
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    # Reception
    queue_number = models.PositiveIntegerField(null=True, blank=True)
    department = models.CharField(max_length=32, choices=Department.choices, blank=True)
    claimed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='claimed_reception_visits')
    claimed_at = models.DateTimeField(null=True, blank=True)
    # Unified assignee for current handler (doctor or lab)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_visits')
    doctor_arrived = models.BooleanField(default=False)
    # Doctor consultation state machine for today's flow
    doctor_status = models.CharField(max_length=16, blank=True, default='')  # '', ready_to_consult, not_done, finished
    # Doctor
    symptoms = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    prescription_notes = models.TextField(blank=True)
    doctor_done = models.BooleanField(default=False)
    doctor_done_at = models.DateTimeField(null=True, blank=True)
    # Lab
    lab_tests = models.TextField(blank=True)
    lab_test_type = models.CharField(max_length=50, blank=True)
    lab_claimed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='claimed_lab_visits')
    lab_claimed_at = models.DateTimeField(null=True, blank=True)
    lab_arrived = models.BooleanField(default=False)
    lab_results = models.TextField(blank=True)
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
    # Specific service/test type, e.g., particular lab department
    service_type = models.ForeignKey('visits.ServiceType', on_delete=models.SET_NULL, null=True, blank=True, help_text='Specific service type selected')

    def __str__(self) -> str:
        return f"{self.patient} - {self.get_service_display()} @ {self.timestamp:%Y-%m-%d %H:%M}"

class ServiceType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    requires_department = models.BooleanField(default=False, help_text='Whether this service requires department selection')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

class Laboratory(models.TextChoices):
    HEMATOLOGY = 'Hematology', 'Hematology (Blood Analysis)'
    CLINICAL_MICROSCOPY = 'Clinical Microscopy', 'Clinical Microscopy (Urine/Stool Exam)'
    CLINICAL_CHEMISTRY = 'Clinical Chemistry', 'Clinical Chemistry (Blood Chemistry)'
    IMMUNOLOGY = 'Immunology and Serology', 'Immunology and Serology (Infectious Disease Tests)'
    MICROBIOLOGY = 'Microbiology', 'Microbiology (Culture and Sensitivity)'
    PATHOLOGY = 'Pathology', 'Pathology (Tissue and Biopsy)'


class LabResult(models.Model):
    visit = models.ForeignKey('visits.Visit', on_delete=models.CASCADE, related_name='lab_result_entries')
    lab_type = models.CharField(max_length=64, choices=Laboratory.choices)
    status = models.CharField(max_length=32, choices=[
        ('queue', 'Queue'),
        ('claimed', 'Claimed'),
        ('in_process', 'In Process'),
        ('done', 'Done'),
        ('not_done', 'Not Done'),
    ], default='queue')
    results = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self) -> str:
        return f"{self.visit_id} · {self.lab_type} · {self.status}"


class VaccinationType(models.TextChoices):
    COVID19 = 'COVID-19 Vaccine', 'COVID-19 Vaccine'
    INFLUENZA = 'Influenza (Flu) Vaccine', 'Influenza (Flu) Vaccine'
    HEPATITIS_B = 'Hepatitis B Vaccine', 'Hepatitis B Vaccine'
    TETANUS = 'Tetanus Vaccine', 'Tetanus Vaccine'
    MMR = 'Measles, Mumps, Rubella (MMR) Vaccine', 'Measles, Mumps, Rubella (MMR) Vaccine'
    POLIO = 'Polio Vaccine', 'Polio Vaccine'
    VARICELLA = 'Varicella (Chickenpox) Vaccine', 'Varicella (Chickenpox) Vaccine'
    HPV = 'Human Papillomavirus (HPV) Vaccine', 'Human Papillomavirus (HPV) Vaccine'


class VaccinationRecord(models.Model):
    visit = models.ForeignKey('visits.Visit', on_delete=models.CASCADE, related_name='vaccination_records')
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='vaccination_records')
    vaccine_type = models.CharField(max_length=64, choices=VaccinationType.choices)
    status = models.CharField(max_length=32, choices=[
        ('queue', 'Queue'),
        ('claimed', 'Claimed'),
        ('in_process', 'In Process'),
        ('done', 'Done'),
        ('not_done', 'Not Done'),
    ], default='queue')
    details = models.JSONField(default=dict, blank=True)
    administered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self) -> str:
        return f"{self.visit_id} · {self.vaccine_type} · {self.status}"

class Diagnosis(models.Model):
    visit = models.ForeignKey('visits.Visit', on_delete=models.CASCADE, related_name='diagnoses')
    text = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_primary', 'id']

    def __str__(self) -> str:
        return f"{'Primary' if self.is_primary else 'Secondary'}: {self.text}"


class PrescriptionItem(models.Model):
    visit = models.ForeignKey('visits.Visit', on_delete=models.CASCADE, related_name='prescriptions')
    medicine = models.CharField(max_length=200)
    dosage = models.CharField(max_length=120, blank=True)
    frequency = models.CharField(max_length=120, blank=True)
    duration = models.CharField(max_length=120, blank=True)
    instructions = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self) -> str:
        return self.medicine
