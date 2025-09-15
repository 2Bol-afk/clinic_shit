from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from patients.models import Patient
from visits.models import Visit

ROLE_GROUPS = [
    'Admin', 'Reception', 'Doctor', 'Laboratory', 'Pharmacy', 'Vaccination', 'Patient'
]

class Command(BaseCommand):
    help = 'Create default groups and assign basic permissions'

    def handle(self, *args, **options):
        for name in ROLE_GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created group {name}'))
        # Assign model-level perms as a baseline (admins usually are superusers)
        patient_ct = ContentType.objects.get_for_model(Patient)
        visit_ct = ContentType.objects.get_for_model(Visit)
        perms = Permission.objects.filter(content_type__in=[patient_ct, visit_ct])
        # Reception: add visits (reception), view patients
        Group.objects.get(name='Reception').permissions.set(perms.filter(codename__in=['view_patient','view_visit','add_visit']))
        # Doctor: view patients, add/change visits
        Group.objects.get(name='Doctor').permissions.set(perms.filter(codename__in=['view_patient','view_visit','add_visit','change_visit']))
        # Laboratory
        Group.objects.get(name='Laboratory').permissions.set(perms.filter(codename__in=['view_patient','view_visit','add_visit','change_visit']))
        # Pharmacy
        Group.objects.get(name='Pharmacy').permissions.set(perms.filter(codename__in=['view_patient','view_visit','add_visit','change_visit']))
        # Vaccination
        Group.objects.get(name='Vaccination').permissions.set(perms.filter(codename__in=['view_patient','view_visit','add_visit','change_visit']))
        # Patient - minimal view of own data handled in views; no model perms needed
        self.stdout.write(self.style.SUCCESS('Roles bootstrapped.'))
