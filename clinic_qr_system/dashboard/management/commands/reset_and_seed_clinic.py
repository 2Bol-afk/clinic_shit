from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.utils import timezone
from patients.models import Patient, Doctor, DEPARTMENT_CHOICES
from visits.models import Visit, LabResult, VaccinationRecord, Prescription, PrescriptionMedicine
from django.conf import settings
import random
from datetime import timedelta


class Command(BaseCommand):
    help = "Delete all app data except superusers, then seed role accounts, 20 patients, and sample transactions. Writes dummy_acc.txt."

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Run non-interactively')

    def handle(self, *args, **options):
        non_interactive = options.get('yes')
        if not non_interactive:
            confirm = input('This will DELETE all non-admin users and all domain data. Continue? [y/N]: ').strip().lower()
            if confirm != 'y':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return

        with transaction.atomic():
            self._purge_domain_data()
            accounts = []
            # Keep existing superusers, record them
            for su in User.objects.filter(is_superuser=True):
                accounts.append((su.username, su.email or f"{su.username}@example.com", '(existing)', 'Admin'))

            # Ensure groups
            groups = {}
            for name in ['Reception', 'Doctor', 'Laboratory', 'Pharmacy', 'Vaccination', 'Patient', 'Admin']:
                groups[name], _ = Group.objects.get_or_create(name=name)

            # Create doctor accounts per department
            dept_to_doctor = {}
            for dept_code, dept_name in DEPARTMENT_CHOICES:
                username = f"doctor_{dept_code.lower().replace(' ', '_').replace('-', '').replace("'", '')}"
                email = f"{username}@clinic.local"
                password = 'Password123!'
                user = User.objects.create_user(username=username, email=email, password=password, first_name='Dr', last_name=dept_code)
                user.is_active = True
                user.save()
                user.groups.add(groups['Doctor'])
                # Create doctor profile
                Doctor.objects.create(user=user, full_name=f"Dr. {dept_code}", specialization=dept_code, must_change_password=False)
                accounts.append((username, email, password, f'Doctor:{dept_code}'))
                dept_to_doctor[dept_code] = user

            # Create staff accounts
            staff_specs = [
                ('reception1', 'Reception'),
                ('lab1', 'Laboratory'),
                ('pharmacy1', 'Pharmacy'),
                ('vaccination1', 'Vaccination'),
            ]
            for uname, role in staff_specs:
                email = f"{uname}@clinic.local"
                password = 'Password123!'
                u = User.objects.create_user(username=uname, email=email, password=password)
                u.is_active = True
                u.save()
                u.groups.add(groups[role])
                accounts.append((uname, email, password, role))

            # Create 20 patients
            patients = []
            for i in range(1, 21):
                uname = f"patient{i:02d}"
                email = f"{uname}@mail.local"
                password = 'Password123!'
                u = User.objects.create_user(username=uname, email=email, password=password, first_name='Patient', last_name=str(i))
                u.is_active = True
                u.save()
                u.groups.add(groups['Patient'])
                p = Patient.objects.create(
                    user=u,
                    full_name=f"Patient {i:02d}",
                    age=random.randint(18, 70),
                    address=f"Street {i}, City",
                    contact=f"0917{random.randint(1000000, 9999999)}",
                    email=email,
                    patient_code=f"P{i:05d}",
                )
                patients.append((u, p))
                accounts.append((uname, email, password, 'Patient'))

            # Create transactions for each patient
            services = Visit.Service
            lab_types = ['urinalysis', 'fecalysis', 'fbs', 'pregnancy', 'lipid', 'rdt', 'blood_typing']
            vacc_types = [choice[0] for choice in VaccinationRecord._meta.get_field('vaccine_type').choices]
            now = timezone.now()

            for u, patient in patients:
                # Doctor visit (link to random doctor)
                dept_code = random.choice([d[0] for d in DEPARTMENT_CHOICES])
                doctor_user = dept_to_doctor.get(dept_code) or random.choice(list(dept_to_doctor.values()))
                v_doc = Visit.objects.create(
                    patient=patient,
                    service=services.DOCTOR,
                    status=Visit.Status.DONE,
                    department=dept_code,
                    doctor_user=doctor_user,
                    symptoms='Headache, fever',
                    diagnosis='Viral syndrome',
                    prescription_notes='Paracetamol 500mg',
                    doctor_done=True,
                    doctor_done_at=now - timedelta(days=random.randint(0, 10)),
                    created_by=doctor_user,
                )
                # Prescription linked to consultation
                pr = Prescription.objects.create(visit=v_doc, doctor=doctor_user, status=Prescription.Status.DISPENSED, dispensed_at=now)
                PrescriptionMedicine.objects.create(prescription=pr, drug_name='Paracetamol', dosage='500mg', frequency='TID', duration='5 days', quantity='15 tablets')

                # Lab request
                v_lab = Visit.objects.create(
                    patient=patient,
                    service=services.LAB,
                    status=Visit.Status.DONE,
                    lab_test_type=random.choice(lab_types),
                    lab_results='All parameters within normal limits',
                    lab_completed=True,
                    lab_completed_at=now - timedelta(days=random.randint(0, 10)),
                    created_by=doctor_user,
                )
                LabResult.objects.create(visit=v_lab, lab_type='Clinical Chemistry', status='done', results={'glucose': 95})

                # Pharmacy (dispensed) – already created via Prescription; ensure status progression
                pr.status = Prescription.Status.DISPENSED
                pr.save(update_fields=['status'])

                # Vaccination record
                v_vac = Visit.objects.create(
                    patient=patient,
                    service=services.VACCINATION,
                    status=Visit.Status.DONE,
                    vaccine_type=random.choice(vacc_types),
                    vaccination_date=(now - timedelta(days=random.randint(0, 30))).date(),
                    created_by=doctor_user,
                )
                VaccinationRecord.objects.create(visit=v_vac, patient=patient, vaccine_type=v_vac.vaccine_type, status='done', details={'batch': f'B{random.randint(1000,9999)}'})

        # Write dummy accounts file
        out_path = getattr(settings, 'BASE_DIR', '.') / 'dummy_acc.txt' if hasattr(settings, 'BASE_DIR') else 'dummy_acc.txt'
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('username,email,password,role\n')
            for username, email, pw, role in accounts:
                f.write(f"{username},{email},{pw},{role}\n")

        self.stdout.write(self.style.SUCCESS(f'Done. Accounts written to {out_path}'))

    def _purge_domain_data(self):
        # Delete all non-superuser users
        User.objects.filter(is_superuser=False).delete()
        # Domain models
        LabResult.objects.all().delete()
        VaccinationRecord.objects.all().delete()
        PrescriptionMedicine.objects.all().delete()
        Prescription.objects.all().delete()
        Visit.objects.all().delete()
        Doctor.objects.all().delete()
        Patient.objects.all().delete()

