from django.contrib import admin
from .models import Visit


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ('patient', 'service', 'timestamp', 'created_by')
    list_filter = ('service', 'timestamp')
    search_fields = ('patient__full_name', 'patient__patient_code')

# Register your models here.
