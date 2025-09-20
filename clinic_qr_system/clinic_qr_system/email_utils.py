"""
Email utility functions for Brevo integration.
Provides convenient functions for sending common types of emails.
"""
import logging
from typing import List, Optional, Dict, Any, Union
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.mail import send_mail as django_send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.template import Context, Template

logger = logging.getLogger(__name__)


def send_email_with_attachment(
    subject: str,
    message: str,
    recipient_list: List[str],
    attachment_data: Optional[Dict[str, Any]] = None,
    html_message: Optional[str] = None,
    from_email: Optional[str] = None,
    fail_silently: bool = False
) -> bool:
    """
    Send email with optional attachment using Brevo.
    
    Args:
        subject: Email subject
        message: Plain text message
        recipient_list: List of recipient email addresses
        attachment_data: Dict with 'filename', 'content', 'mimetype' keys
        html_message: Optional HTML version of the message
        from_email: Sender email (uses DEFAULT_FROM_EMAIL if not provided)
        fail_silently: Whether to fail silently on errors
        
    Returns:
        bool: True if email was sent successfully
    """
    try:
        from_email = from_email or settings.DEFAULT_FROM_EMAIL
        
        if html_message:
            # Use EmailMultiAlternatives for HTML content
            email = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=from_email,
                to=recipient_list
            )
            email.attach_alternative(html_message, "text/html")
        else:
            email = EmailMessage(
                subject=subject,
                body=message,
                from_email=from_email,
                to=recipient_list
            )
        
        # Add attachment if provided
        if attachment_data:
            email.attach(
                attachment_data['filename'],
                attachment_data['content'],
                attachment_data.get('mimetype', 'application/octet-stream')
            )
        
        result = email.send(fail_silently=fail_silently)
        
        if result:
            logger.info(f"Email sent successfully to {recipient_list}")
        else:
            logger.warning(f"Email sending returned 0 for {recipient_list}")
            
        return bool(result)
        
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        if not fail_silently:
            raise
        return False


def send_patient_registration_email(
    patient_name: str,
    patient_code: str,
    patient_email: str,
    qr_code_data: Optional[bytes] = None,
    qr_filename: str = "qr_code.png",
    temp_password: Optional[str] = None,
    username: Optional[str] = None
) -> bool:
    """
    Send patient registration confirmation email with QR code.
    
    Args:
        patient_name: Patient's full name
        patient_code: Patient's unique code
        patient_email: Patient's email address
        qr_code_data: QR code image data (bytes)
        qr_filename: Filename for QR code attachment
        temp_password: Temporary password (if applicable)
        username: Username for login (if applicable)
        
    Returns:
        bool: True if email was sent successfully
    """
    # Prepare email content
    subject = "Your Patient QR Code and Registration Details"
    
    message_parts = [
        f"Dear {patient_name},\n",
        "\nThank you for registering with Clinic QR System.\n",
        f"Your Patient Code is: {patient_code}\n",
    ]
    
    if username:
        message_parts.append(f"Portal Username: {username}\n")
    
    if temp_password:
        message_parts.append(f"Temporary Password: {temp_password}\n")
        message_parts.append("\nPlease log in using the temporary password and change it on your first login.\n")
    
    message_parts.extend([
        "\nPlease keep this email for future reference.\n",
        "You can use the attached QR code for faster check-in at the reception.\n\n",
        "Regards,\nClinic QR System"
    ])
    
    message = ''.join(message_parts)
    
    # Prepare attachment data
    attachment_data = None
    if qr_code_data:
        attachment_data = {
            'filename': qr_filename,
            'content': qr_code_data,
            'mimetype': 'image/png'
        }
    
    return send_email_with_attachment(
        subject=subject,
        message=message,
        recipient_list=[patient_email],
        attachment_data=attachment_data,
        fail_silently=False
    )


def send_test_email(
    recipient_email: str,
    message: str = "This is a test email from Clinic QR System using Brevo.",
    subject: str = "Brevo SMTP Test"
) -> bool:
    """
    Send a test email to verify Brevo configuration.
    
    Args:
        recipient_email: Email address to send test to
        message: Test message content
        subject: Test email subject
        
    Returns:
        bool: True if email was sent successfully
    """
    try:
        result = django_send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False
        )
        
        if result:
            logger.info(f"Test email sent successfully to {recipient_email}")
        else:
            logger.warning(f"Test email sending returned 0 for {recipient_email}")
            
        return bool(result)
        
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        raise


def send_notification_email(
    recipient_list: List[str],
    subject: str,
    message: str,
    html_message: Optional[str] = None,
    from_email: Optional[str] = None
) -> bool:
    """
    Send a notification email (no attachments).
    
    Args:
        recipient_list: List of recipient email addresses
        subject: Email subject
        message: Plain text message
        html_message: Optional HTML version
        from_email: Sender email
        
    Returns:
        bool: True if email was sent successfully
    """
    return send_email_with_attachment(
        subject=subject,
        message=message,
        recipient_list=recipient_list,
        html_message=html_message,
        from_email=from_email,
        fail_silently=False
    )


def get_email_provider_info() -> Dict[str, Any]:
    """
    Get information about the current email provider configuration.
    
    Returns:
        Dict with provider information
    """
    provider = getattr(settings, 'EMAIL_PROVIDER', 'unknown')
    
    info = {
        'provider': provider,
        'backend': getattr(settings, 'EMAIL_BACKEND', 'unknown'),
        'from_email': getattr(settings, 'DEFAULT_FROM_EMAIL', 'unknown'),
    }
    
    if provider == 'brevo':
        info.update({
            'api_key_configured': bool(getattr(settings, 'BREVO_API_KEY', None)),
            'sender_email': getattr(settings, 'BREVO_SENDER_EMAIL', 'unknown'),
            'sender_name': getattr(settings, 'BREVO_SENDER_NAME', 'unknown'),
            'smtp_host': getattr(settings, 'BREVO_SMTP_HOST', 'unknown'),
            'smtp_port': getattr(settings, 'BREVO_SMTP_PORT', 'unknown'),
        })
    elif provider == 'gmail':
        info.update({
            'smtp_host': getattr(settings, 'EMAIL_HOST', 'unknown'),
            'smtp_port': getattr(settings, 'EMAIL_PORT', 'unknown'),
            'use_tls': getattr(settings, 'EMAIL_USE_TLS', False),
        })
    
    return info
