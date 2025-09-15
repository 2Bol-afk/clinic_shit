from django.contrib import admin
from .models import Patient, StaffProfile, Doctor


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'patient_code', 'age', 'created_at')
    search_fields = ('full_name', 'email', 'patient_code')


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'specialization', 'user')
    search_fields = ('full_name', 'specialization', 'user__username', 'user__email')

# Register your models here.
