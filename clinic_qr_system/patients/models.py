from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User


DEPARTMENT_CHOICES = [
    ('General Medicine', 'General Medicine'),
    ('Pediatrics', 'Pediatrics'),
    ('OB-GYN', 'OB-GYN'),
    ('Others', 'Others'),
]

class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='patient_profile')
    full_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    address = models.TextField()
    contact = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    patient_code = models.CharField(max_length=20, unique=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.full_name} ({self.patient_code})"


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        RECEPTION = 'reception', 'Receptionist/Triage'
        DOCTOR = 'doctor', 'Doctor'
        LAB = 'lab', 'Laboratory Staff'
        PHARMACY = 'pharmacy', 'Pharmacist'
        VACCINATION = 'vaccination_staff', 'Vaccination Staff'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=32, choices=Role.choices)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.get_role_display()})"


class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    full_name = models.CharField(max_length=255)
    specialization = models.CharField('Department', max_length=100, choices=DEPARTMENT_CHOICES)

    def __str__(self) -> str:
        return f"Dr. {self.full_name} ({self.specialization})"

# Create your models here.
