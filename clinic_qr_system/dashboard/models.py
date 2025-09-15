from django.db import models
from django.conf import settings

# Create your models here.

class ActivityLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    verb = models.CharField(max_length=100)
    description = models.TextField()
    patient = models.ForeignKey('patients.Patient', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.verb}"
