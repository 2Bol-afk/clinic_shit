from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import VaccineType, PatientVaccination, VaccineDose, VaccinationReminder


@admin.register(VaccineType)
class VaccineTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'total_doses_required', 'age_minimum', 'age_maximum', 'is_active', 'created_at']
    list_filter = ['is_active', 'total_doses_required', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    ordering = ['name']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Dose Requirements', {
            'fields': ('total_doses_required', 'dose_intervals')
        }),
        ('Age Requirements', {
            'fields': ('age_minimum', 'age_maximum')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('patient_vaccinations')


@admin.register(PatientVaccination)
class PatientVaccinationAdmin(admin.ModelAdmin):
    list_display = [
        'patient_name', 'vaccine_type', 'started_date', 'completion_status', 
        'progress_percentage', 'next_dose_date', 'is_overdue_status'
    ]
    list_filter = ['completed', 'vaccine_type', 'started_date', 'created_at']
    search_fields = ['patient__full_name', 'patient__patient_code', 'vaccine_type__name']
    readonly_fields = ['created_at', 'completion_date']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Patient Information', {
            'fields': ('patient', 'vaccine_type')
        }),
        ('Vaccination Details', {
            'fields': ('started_date', 'completed', 'completion_date', 'notes')
        }),
        ('System Information', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def patient_name(self, obj):
        return obj.patient.full_name
    patient_name.short_description = 'Patient'
    patient_name.admin_order_field = 'patient__full_name'
    
    def completion_status(self, obj):
        if obj.completed:
            return format_html('<span style="color: green;">✓ Completed</span>')
        else:
            return format_html('<span style="color: orange;">⏳ In Progress</span>')
    completion_status.short_description = 'Status'
    
    def progress_percentage(self, obj):
        percentage = obj.get_completion_percentage()
        color = 'green' if percentage == 100 else 'orange'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, percentage)
    progress_percentage.short_description = 'Progress'
    
    def next_dose_date(self, obj):
        next_date = obj.get_next_dose_date()
        if next_date:
            if next_date < timezone.now().date():
                return format_html('<span style="color: red;">{}</span>', next_date)
            else:
                return str(next_date)
        return '-'
    next_dose_date.short_description = 'Next Dose'
    
    def is_overdue_status(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red;">⚠ Overdue</span>')
        return format_html('<span style="color: green;">✓ On Track</span>')
    is_overdue_status.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('patient', 'vaccine_type', 'created_by')


@admin.register(VaccineDose)
class VaccineDoseAdmin(admin.ModelAdmin):
    list_display = [
        'vaccination_info', 'dose_number', 'scheduled_date', 'administered_status',
        'administered_date', 'administered_by', 'is_overdue_status'
    ]
    list_filter = [
        'administered', 'scheduled_date', 'administered_date', 
        'vaccination__vaccine_type', 'created_at'
    ]
    search_fields = [
        'vaccination__patient__full_name', 'vaccination__patient__patient_code',
        'vaccination__vaccine_type__name', 'batch_number'
    ]
    readonly_fields = ['created_at']
    ordering = ['-scheduled_date']
    
    fieldsets = (
        ('Vaccination Information', {
            'fields': ('vaccination', 'dose_number', 'scheduled_date')
        }),
        ('Administration Details', {
            'fields': ('administered', 'administered_date', 'administered_by', 'site_of_injection')
        }),
        ('Vaccine Information', {
            'fields': ('batch_number', 'expiry_date')
        }),
        ('Additional Information', {
            'fields': ('adverse_reactions', 'notes')
        }),
        ('System Information', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def vaccination_info(self, obj):
        return f"{obj.vaccination.patient.full_name} - {obj.vaccination.vaccine_type.name}"
    vaccination_info.short_description = 'Patient - Vaccine'
    vaccination_info.admin_order_field = 'vaccination__patient__full_name'
    
    def administered_status(self, obj):
        if obj.administered:
            return format_html('<span style="color: green;">✓ Administered</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pending</span>')
    administered_status.short_description = 'Status'
    
    def is_overdue_status(self, obj):
        if obj.is_overdue():
            return format_html('<span style="color: red;">⚠ Overdue</span>')
        elif obj.administered:
            return format_html('<span style="color: green;">✓ Completed</span>')
        else:
            return format_html('<span style="color: blue;">📅 Scheduled</span>')
    is_overdue_status.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'vaccination__patient', 'vaccination__vaccine_type', 'administered_by'
        )


@admin.register(VaccinationReminder)
class VaccinationReminderAdmin(admin.ModelAdmin):
    list_display = [
        'dose_info', 'reminder_date', 'sent_status', 'sent_at', 'email_sent', 'sms_sent'
    ]
    list_filter = ['sent', 'email_sent', 'sms_sent', 'reminder_date', 'created_at']
    search_fields = [
        'dose__vaccination__patient__full_name',
        'dose__vaccination__vaccine_type__name'
    ]
    readonly_fields = ['created_at', 'sent_at']
    ordering = ['-reminder_date']
    
    def dose_info(self, obj):
        return f"{obj.dose.vaccination.patient.full_name} - {obj.dose.vaccination.vaccine_type.name} (Dose {obj.dose.dose_number})"
    dose_info.short_description = 'Patient - Vaccine (Dose)'
    
    def sent_status(self, obj):
        if obj.sent:
            return format_html('<span style="color: green;">✓ Sent</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pending</span>')
    sent_status.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'dose__vaccination__patient', 'dose__vaccination__vaccine_type'
        )


# Custom admin site configuration
admin.site.site_header = "Clinic QR System - Vaccination Management"
admin.site.site_title = "Vaccination Admin"
admin.site.index_title = "Vaccination Administration"
