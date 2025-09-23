import qrcode
import os
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import Patient


def generate_qr_code(patient):
    """Generate QR code for a patient and save it to the file system"""
    try:
        # Create QR code with patient email
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(patient.email)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to media directory
        qr_filename = f"qr_{patient.patient_code}.png"
        qr_path = os.path.join(settings.MEDIA_ROOT, 'qr_codes', qr_filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(qr_path), exist_ok=True)
        
        # Save image
        img.save(qr_path)
        
        # Update patient record
        patient.qr_code = f"qr_codes/{qr_filename}"
        patient.save(update_fields=['qr_code'])
        
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
        
        # Attach QR code
        if patient.qr_code:
            qr_path = os.path.join(settings.MEDIA_ROOT, patient.qr_code.name)
            if os.path.exists(qr_path):
                with open(qr_path, 'rb') as f:
                    email.attach(f"qr_code_{patient.patient_code}.png", f.read(), 'image/png')
        
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
