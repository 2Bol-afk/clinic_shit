from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.conf import settings
from patients.models import Patient
from visits.models import Visit, ServiceType
from io import BytesIO
import qrcode
import uuid
import re
from clinic_qr_system.email_utils import send_patient_registration_email


class Command(BaseCommand):
    help = 'Interactive test: create a patient, generate QR, email it, then clean up.'

    def _prompt(self, label: str, required: bool = True, validator=None):
        while True:
            val = input(f"{label}: ").strip()
            if not val and required:
                print("This field is required.")
                continue
            if validator and val and not validator(val):
                print("Invalid value, please try again.")
                continue
            return val

    def handle(self, *args, **options):
        print("Enter patient details for test (these will be emailed, then removed from DB):")
        full_name = self._prompt("Full Name")
        age_str = self._prompt("Age", validator=lambda x: x.isdigit())
        contact = self._prompt("Contact")
        address = self._prompt("Address")
        email = self._prompt(
            "Email",
            validator=lambda x: re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', x) is not None,
        )
        visit_type = self._prompt("Visit Type (consultation/laboratory/vaccination)", validator=lambda x: x in ["consultation", "laboratory", "vaccination"]).lower()
        department = ''
        if visit_type == 'consultation':
            department = self._prompt("Department (e.g., Pediatrics, OB-GYN, Cardiology, etc.)")

        # Create patient with auto code
        age = int(age_str or 0)
        patient_code = uuid.uuid4().hex[:10].upper()
        patient = Patient.objects.create(
            full_name=full_name,
            age=age,
            address=address,
            contact=contact,
            email=email,
            patient_code=patient_code,
        )

        # Generate QR containing email + patient id
        file_name = f"qr_{patient.patient_code}.png"
        buffer = None
        try:
            qr_payload = f"email:{patient.email};id:{patient.id}"
            qr_img = qrcode.make(qr_payload)
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            patient.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
            patient.save(update_fields=['qr_code'])
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"QR generation failed: {e}"))

        # Queue a reception visit to simulate normal flow
        today = Visit.objects.model.timestamp.field.auto_now_add if hasattr(Visit, 'timestamp') else None
        kwargs = {
            'patient': patient,
            'service': 'reception',
            'status': Visit.Status.QUEUED,
            'department': department if visit_type == 'consultation' else '',
        }
        if visit_type == 'consultation':
            # Basic queue assignment for the department
            from django.utils import timezone
            d = department
            last = (Visit.objects
                    .filter(service='reception', timestamp__date=timezone.localdate(), department=d)
                    .order_by('-queue_number')
                    .first())
            kwargs['queue_number'] = (last.queue_number + 1) if last and last.queue_number else 1
        else:
            # Tag notes and set service_type
            tag = 'Laboratory' if visit_type == 'laboratory' else 'Vaccination'
            kwargs['notes'] = f"[Visit: {tag}]"
            from django.utils import timezone
            last = (Visit.objects
                    .filter(service='reception', timestamp__date=timezone.localdate(), department='')
                    .filter(notes__icontains=f'[visit: {tag.lower()}]')
                    .order_by('-queue_number')
                    .first())
            kwargs['queue_number'] = (last.queue_number + 1) if last and last.queue_number else 1
            svc = ServiceType.objects.filter(name__iexact=tag).first()
            if svc:
                kwargs['service_type'] = svc
        visit = Visit.objects.create(**kwargs)
        
        # Send queue notification email
        try:
            from clinic_qr_system.email_utils import send_queue_notification_email_html
            
            # Determine service type for email
            if visit_type == 'consultation':
                service_type = 'consultation'
                department = department
            elif visit_type == 'laboratory':
                service_type = 'laboratory'
                department = None
            elif visit_type == 'vaccination':
                service_type = 'vaccination'
                department = None
            else:
                service_type = visit_type
                department = department
            
            # Send queue notification email
            email_sent = send_queue_notification_email_html(
                patient_name=patient.full_name,
                patient_email=patient.email,
                queue_number=visit.queue_number,
                service_type=service_type,
                department=department,
                visit_id=visit.id
            )
            
            if email_sent:
                self.stdout.write(self.style.SUCCESS(f"Queue notification email sent to {patient.email}."))
            else:
                self.stdout.write(self.style.WARNING(f"Queue notification email failed to send to {patient.email}."))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Queue notification email failed: {e}"))

        self.stdout.write(self.style.SUCCESS("Patient created successfully."))
        if patient.qr_code:
            self.stdout.write(f"QR Code generated: {patient.qr_code.path}")
        else:
            self.stdout.write("QR Code not available.")

        # Email using Brevo
        try:
            # Prepare QR code data
            qr_data = None
            qr_filename = file_name
            
            if patient.qr_code and hasattr(patient.qr_code, 'path'):
                with open(patient.qr_code.path, 'rb') as f:
                    qr_data = f.read()
            elif buffer:
                qr_data = buffer.getvalue()
            
            # Send email using Brevo utility
            sent = send_patient_registration_email(
                patient_name=patient.full_name,
                patient_code=patient.patient_code,
                patient_email=patient.email,
                qr_code_data=qr_data,
                qr_filename=qr_filename
            )
            
            if sent:
                self.stdout.write(self.style.SUCCESS(f"Email sent to: {patient.email} via Brevo"))
            else:
                self.stdout.write(self.style.WARNING(f"Email not sent to: {patient.email}"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Email failed: {e}"))

        # Cleanup (delete patient after test)
        try:
            # Remove associated user if any, and then patient
            usr = getattr(patient, 'user', None)
            patient.delete()
            if usr:
                usr.delete()
            self.stdout.write(self.style.SUCCESS("Test data cleaned up (patient deleted)."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Cleanup warning: {e}"))


