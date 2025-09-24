import qrcode
import os
from django.conf import settings
from django.core.mail import send_mail
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from .models import Patient


def generate_qr_code(patient):
    """Generate QR code for a patient and save via Django storage (Cloudinary/local)."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(patient.email)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        qr_filename = f"qr_{patient.patient_code}.png"

        # Save through the ImageField to active storage
        from io import BytesIO
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        patient.qr_code.save(qr_filename, ContentFile(buffer.getvalue()), save=True)

        return True
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return False


def send_qr_code_email(patient):
    """Send QR code to patient's email"""
    try:
        if not patient.qr_code:
            generate_qr_code(patient)
        
        subject = "Your Clinic QR Code"
        message = f"""
        Dear {patient.full_name},
        
        Your QR code has been generated and is attached to this email.
        Please keep this QR code safe as it will be used for quick check-in at the clinic.
        
        Patient ID: {patient.patient_code}
        
        Best regards,
        Clinic Management System
        """
        
        # Send email with QR code attachment
        from django.core.mail import EmailMessage
        from django.core.files import File
        
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[patient.email],
        )
        
        # Attach QR code using storage
        if patient.qr_code:
            try:
                with patient.qr_code.open('rb') as f:
                    email.attach(f"qr_code_{patient.patient_code}.png", f.read(), 'image/png')
            except Exception:
                pass
        
        email.send()
        return True
    except Exception as e:
        print(f"Error sending QR code email: {e}")
        return False


def generate_temp_password():
    """Generate a temporary password for new staff"""
    import secrets
    import string
    
    # Generate 8-character password with letters and numbers
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for i in range(8))
    return password
