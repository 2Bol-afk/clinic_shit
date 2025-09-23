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


def send_queue_notification_email(
    patient_name: str,
    patient_email: str,
    queue_number: int,
    service_type: str,
    department: str = None,
    visit_id: int = None
) -> bool:
    """
    Send queue notification email to patient.
    
    Args:
        patient_name: Patient's full name
        patient_email: Patient's email address
        queue_number: Queue number assigned
        service_type: Type of service (laboratory, consultation, vaccination)
        department: Department name (for consultation)
        visit_id: Visit ID for reference
        
    Returns:
        bool: True if email was sent successfully
    """
    try:
        # Determine subject and content based on service type
        if service_type.lower() == 'laboratory':
            subject = "You Have Been Queued for Laboratory"
            message_parts = [
                f"Dear {patient_name},\n",
                "\nYou have been successfully added to the laboratory queue.\n",
                f"Your queue number is: {queue_number}\n",
                "\nPlease proceed to the laboratory when your number is called.\n",
                "The laboratory staff will assist you with your tests.\n\n",
                "Thank you for your patience.\n\n",
                "Regards,\nClinic QR System"
            ]
        elif service_type.lower() == 'consultation':
            subject = "You Have Been Queued for Consultation"
            dept_text = f" in the {department} department" if department else ""
            message_parts = [
                f"Dear {patient_name},\n",
                f"\nYou have been successfully added to the consultation queue{dept_text}.\n",
                f"Your queue number is: {queue_number}\n",
                f"Department: {department or 'General Consultation'}\n",
                "\nPlease wait in the designated area until your number is called.\n",
                "A doctor will see you shortly.\n\n",
                "Thank you for your patience.\n\n",
                "Regards,\nClinic QR System"
            ]
        elif service_type.lower() == 'vaccination':
            subject = "You Have Been Queued for Vaccination"
            message_parts = [
                f"Dear {patient_name},\n",
                "\nYou have been successfully added to the vaccination queue.\n",
                f"Your queue number is: {queue_number}\n",
                "\nPlease proceed to the vaccination area when your number is called.\n",
                "The vaccination staff will assist you with your immunization.\n\n",
                "Thank you for your patience.\n\n",
                "Regards,\nClinic QR System"
            ]
        else:
            # Generic queue notification
            subject = "You Have Been Added to the Queue"
            message_parts = [
                f"Dear {patient_name},\n",
                f"\nYou have been successfully added to the {service_type} queue.\n",
                f"Your queue number is: {queue_number}\n",
                "\nPlease wait until your number is called.\n",
                "Staff will assist you shortly.\n\n",
                "Thank you for your patience.\n\n",
                "Regards,\nClinic QR System"
            ]
        
        message = ''.join(message_parts)
        
        # Add visit ID to message if provided
        if visit_id:
            message += f"\n\nReference ID: {visit_id}"
        
        # Send the email
        result = send_notification_email(
            recipient_list=[patient_email],
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        )
        
        if result:
            logger.info(f"Queue notification email sent successfully to {patient_name} ({patient_email}) for {service_type} queue #{queue_number}")
        else:
            logger.warning(f"Queue notification email failed to send to {patient_name} ({patient_email})")
            
        return result
        
    except Exception as e:
        logger.error(f"Failed to send queue notification email to {patient_name} ({patient_email}): {e}")
        return False


def send_queue_notification_email_html(
    patient_name: str,
    patient_email: str,
    queue_number: int,
    service_type: str,
    department: str = None,
    visit_id: int = None
) -> bool:
    """
    Send queue notification email to patient with HTML formatting.
    
    Args:
        patient_name: Patient's full name
        patient_email: Patient's email address
        queue_number: Queue number assigned
        service_type: Type of service (laboratory, consultation, vaccination)
        department: Department name (for consultation)
        visit_id: Visit ID for reference
        
    Returns:
        bool: True if email was sent successfully
    """
    try:
        # Determine subject and content based on service type
        if service_type.lower() == 'laboratory':
            subject = "You Have Been Queued for Laboratory"
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c5aa0; border-bottom: 2px solid #2c5aa0; padding-bottom: 10px;">
                        Laboratory Queue Notification
                    </h2>
                    
                    <p>Dear <strong>{patient_name}</strong>,</p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #2c5aa0; margin-top: 0;">Queue Information</h3>
                        <p><strong>Queue Number:</strong> <span style="font-size: 24px; color: #dc3545; font-weight: bold;">{queue_number}</span></p>
                        <p><strong>Service:</strong> Laboratory</p>
                    </div>
                    
                    <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h4 style="color: #2c5aa0; margin-top: 0;">Instructions</h4>
                        <ul>
                            <li>Please proceed to the <strong>Laboratory</strong> when your number is called</li>
                            <li>The laboratory staff will assist you with your tests</li>
                            <li>Please have your patient ID ready</li>
                        </ul>
                    </div>
                    
                    <p>Thank you for your patience.</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        Regards,<br>
                        Clinic QR System<br>
                        {f'<br>Reference ID: {visit_id}' if visit_id else ''}
                    </p>
                </div>
            </body>
            </html>
            """
        elif service_type.lower() == 'consultation':
            subject = "You Have Been Queued for Consultation"
            dept_text = f" in the {department} department" if department else ""
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c5aa0; border-bottom: 2px solid #2c5aa0; padding-bottom: 10px;">
                        Consultation Queue Notification
                    </h2>
                    
                    <p>Dear <strong>{patient_name}</strong>,</p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #2c5aa0; margin-top: 0;">Queue Information</h3>
                        <p><strong>Queue Number:</strong> <span style="font-size: 24px; color: #dc3545; font-weight: bold;">{queue_number}</span></p>
                        <p><strong>Service:</strong> Doctor Consultation</p>
                        <p><strong>Department:</strong> {department or 'General Consultation'}</p>
                    </div>
                    
                    <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h4 style="color: #2c5aa0; margin-top: 0;">Instructions</h4>
                        <ul>
                            <li>Please wait in the designated waiting area</li>
                            <li>A doctor will see you when your number is called</li>
                            <li>Please have your patient ID and any relevant documents ready</li>
                        </ul>
                    </div>
                    
                    <p>Thank you for your patience.</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        Regards,<br>
                        Clinic QR System<br>
                        {f'<br>Reference ID: {visit_id}' if visit_id else ''}
                    </p>
                </div>
            </body>
            </html>
            """
        elif service_type.lower() == 'vaccination':
            subject = "You Have Been Queued for Vaccination"
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c5aa0; border-bottom: 2px solid #2c5aa0; padding-bottom: 10px;">
                        Vaccination Queue Notification
                    </h2>
                    
                    <p>Dear <strong>{patient_name}</strong>,</p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #2c5aa0; margin-top: 0;">Queue Information</h3>
                        <p><strong>Queue Number:</strong> <span style="font-size: 24px; color: #dc3545; font-weight: bold;">{queue_number}</span></p>
                        <p><strong>Service:</strong> Vaccination/Immunization</p>
                    </div>
                    
                    <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h4 style="color: #2c5aa0; margin-top: 0;">Instructions</h4>
                        <ul>
                            <li>Please proceed to the <strong>Vaccination Area</strong> when your number is called</li>
                            <li>The vaccination staff will assist you with your immunization</li>
                            <li>Please have your patient ID ready</li>
                        </ul>
                    </div>
                    
                    <p>Thank you for your patience.</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        Regards,<br>
                        Clinic QR System<br>
                        {f'<br>Reference ID: {visit_id}' if visit_id else ''}
                    </p>
                </div>
            </body>
            </html>
            """
        else:
            # Generic queue notification
            subject = "You Have Been Added to the Queue"
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c5aa0; border-bottom: 2px solid #2c5aa0; padding-bottom: 10px;">
                        Queue Notification
                    </h2>
                    
                    <p>Dear <strong>{patient_name}</strong>,</p>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="color: #2c5aa0; margin-top: 0;">Queue Information</h3>
                        <p><strong>Queue Number:</strong> <span style="font-size: 24px; color: #dc3545; font-weight: bold;">{queue_number}</span></p>
                        <p><strong>Service:</strong> {service_type.title()}</p>
                    </div>
                    
                    <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h4 style="color: #2c5aa0; margin-top: 0;">Instructions</h4>
                        <ul>
                            <li>Please wait until your number is called</li>
                            <li>Staff will assist you shortly</li>
                            <li>Please have your patient ID ready</li>
                        </ul>
                    </div>
                    
                    <p>Thank you for your patience.</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    <p style="color: #666; font-size: 12px;">
                        Regards,<br>
                        Clinic QR System<br>
                        {f'<br>Reference ID: {visit_id}' if visit_id else ''}
                    </p>
                </div>
            </body>
            </html>
            """
        
        # Create plain text version
        plain_text = f"""
Dear {patient_name},

You have been successfully added to the {service_type} queue.
Your queue number is: {queue_number}
{f'Department: {department}' if department else ''}

Please wait until your number is called.
Staff will assist you shortly.

Thank you for your patience.

Regards,
Clinic QR System
{f'Reference ID: {visit_id}' if visit_id else ''}
        """.strip()
        
        # Send the email with HTML content
        result = send_email_with_attachment(
            subject=subject,
            message=plain_text,
            recipient_list=[patient_email],
            html_message=html_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            fail_silently=False
        )
        
        if result:
            logger.info(f"Queue notification email (HTML) sent successfully to {patient_name} ({patient_email}) for {service_type} queue #{queue_number}")
        else:
            logger.warning(f"Queue notification email (HTML) failed to send to {patient_name} ({patient_email})")
            
        return result
        
    except Exception as e:
        logger.error(f"Failed to send queue notification email (HTML) to {patient_name} ({patient_email}): {e}")
        return False


def send_lab_result_email(
    patient_name: str,
    patient_email: str,
    lab_type: str,
    lab_results: str,
    visit_id: int,
    completed_at: str,
    attachment_data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Send lab result completion email to patient with results attachment.
    
    Args:
        patient_name: Patient's full name
        patient_email: Patient's email address
        lab_type: Type of lab test performed
        lab_results: Lab test results text
        visit_id: Visit ID for reference
        completed_at: Date/time when lab was completed
        attachment_data: Optional PDF attachment data
        
    Returns:
        bool: True if email was sent successfully
    """
    try:
        subject = "Your Lab Result is Ready"
        
        # Create HTML content
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c5aa0; border-bottom: 2px solid #2c5aa0; padding-bottom: 10px;">
                    Lab Result Notification
                </h2>
                
                <p>Dear <strong>{patient_name}</strong>,</p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="color: #2c5aa0; margin-top: 0;">Lab Test Information</h3>
                    <p><strong>Test Type:</strong> {lab_type}</p>
                    <p><strong>Completed:</strong> {completed_at}</p>
                    <p><strong>Visit ID:</strong> {visit_id}</p>
                </div>
                
                <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h4 style="color: #2c5aa0; margin-top: 0;">Test Results</h4>
                    <div style="background-color: white; padding: 10px; border-radius: 3px; font-family: monospace; white-space: pre-wrap;">{lab_results}</div>
                </div>
                
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <h4 style="color: #856404; margin-top: 0;">Important Instructions</h4>
                    <ul style="color: #856404;">
                        <li>Please review your lab results carefully</li>
                        <li>If you have any questions about your results, please contact your doctor</li>
                        <li>You can log in to your patient portal to view your complete medical history</li>
                        <li>If you need to visit the clinic, please bring this email or your patient ID</li>
                    </ul>
                </div>
                
                <p>If you have any questions or concerns about your lab results, please don't hesitate to contact us.</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    Regards,<br>
                    Clinic QR System<br>
                    Laboratory Department
                </p>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        plain_text = f"""
Dear {patient_name},

Your lab result is ready!

Test Information:
- Test Type: {lab_type}
- Completed: {completed_at}
- Visit ID: {visit_id}

Test Results:
{lab_results}

Important Instructions:
- Please review your lab results carefully
- If you have any questions about your results, please contact your doctor
- You can log in to your patient portal to view your complete medical history
- If you need to visit the clinic, please bring this email or your patient ID

If you have any questions or concerns about your lab results, please don't hesitate to contact us.

Regards,
Clinic QR System
Laboratory Department
        """.strip()
        
        # Send the email with attachment
        result = send_email_with_attachment(
            subject=subject,
            message=plain_text,
            recipient_list=[patient_email],
            html_message=html_content,
            attachment_data=attachment_data,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            fail_silently=False
        )
        
        if result:
            logger.info(f"Lab result email sent successfully to {patient_name} ({patient_email}) for {lab_type} test")
        else:
            logger.warning(f"Lab result email failed to send to {patient_name} ({patient_email})")
            
        return result
        
    except Exception as e:
        logger.error(f"Failed to send lab result email to {patient_name} ({patient_email}): {e}")
        return False


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
