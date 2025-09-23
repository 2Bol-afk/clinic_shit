from django.db import models
from django.contrib.auth.models import User


class AuditLog(models.Model):
    """Model to track system activity and user actions"""
    
    ACTION_CHOICES = [
        ('LOGIN', 'User Login'),
        ('LOGOUT', 'User Logout'),
        ('CREATE_USER', 'Create User'),
        ('UPDATE_USER', 'Update User'),
        ('DELETE_USER', 'Delete User'),
        ('RESET_PASSWORD', 'Reset Password'),
        ('TOGGLE_USER_STATUS', 'Enable/Disable User'),
        ('CREATE_PATIENT', 'Create Patient'),
        ('UPDATE_PATIENT', 'Update Patient'),
        ('DELETE_PATIENT', 'Delete Patient'),
        ('RESEND_QR_CODE', 'Resend QR Code'),
        ('CREATE_VISIT', 'Create Visit'),
        ('UPDATE_VISIT', 'Update Visit'),
        ('DELETE_VISIT', 'Delete Visit'),
        ('CREATE_PRESCRIPTION', 'Create Prescription'),
        ('UPDATE_PRESCRIPTION', 'Update Prescription'),
        ('DISPENSE_MEDICINE', 'Dispense Medicine'),
        ('CREATE_LAB_RESULT', 'Create Lab Result'),
        ('UPDATE_LAB_RESULT', 'Update Lab Result'),
        ('CREATE_VACCINATION', 'Create Vaccination'),
        ('UPDATE_VACCINATION', 'Update Vaccination'),
        ('SYSTEM_ACTION', 'System Action'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    details = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.user} - {self.timestamp}"


class ActivityLog(models.Model):
    """Legacy model for backward compatibility - use AuditLog instead"""
    
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='activity_logs', null=True, blank=True)
    patient = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL, null=True, blank=True)
    verb = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.actor} - {self.verb} - {self.created_at}"