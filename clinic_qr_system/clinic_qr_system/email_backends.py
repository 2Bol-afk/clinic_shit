"""
Custom email backends for Brevo (formerly Sendinblue) integration.
"""
import logging
from typing import List, Optional, Dict, Any
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    BREVO_AVAILABLE = True
except ImportError:
    BREVO_AVAILABLE = False
    logger.warning("Brevo SDK not available. Install sib-api-v3-sdk package.")


class BrevoEmailBackend(BaseEmailBackend):
    """
    Custom email backend for Brevo API integration.
    Provides better reliability and features compared to SMTP.
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        
        if not BREVO_AVAILABLE:
            raise ImproperlyConfigured(
                "Brevo SDK is not installed. Please install sib-api-v3-sdk."
            )
        
        self.api_key = getattr(settings, 'BREVO_API_KEY', None)
        if not self.api_key:
            raise ImproperlyConfigured(
                "BREVO_API_KEY is required for BrevoEmailBackend."
            )
        
        # Configure API client
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = self.api_key
        
        self.api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )
        
        self.sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', None)
        self.sender_name = getattr(settings, 'BREVO_SENDER_NAME', 'Clinic QR System')
        
        if not self.sender_email:
            raise ImproperlyConfigured(
                "BREVO_SENDER_EMAIL is required for BrevoEmailBackend."
            )

    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        """
        Send multiple email messages using Brevo API.
        """
        if not email_messages:
            return 0
        
        sent_count = 0
        
        for message in email_messages:
            try:
                if self._send_single_message(message):
                    sent_count += 1
            except Exception as e:
                if not self.fail_silently:
                    raise
                logger.error(f"Failed to send email via Brevo: {e}")
        
        return sent_count

    def _send_single_message(self, message: EmailMessage) -> bool:
        """
        Send a single email message using Brevo API.
        """
        try:
            # Prepare sender
            sender = sib_api_v3_sdk.SendSmtpEmailSender(
                email=self.sender_email,
                name=self.sender_name
            )
            
            # Prepare recipients
            to_recipients = []
            for email in message.to:
                # Extract name from email if it's in format "Name <email@domain.com>"
                recipient_name = email
                if '<' in email and '>' in email:
                    # Format: "Name <email@domain.com>"
                    recipient_name = email.split('<')[0].strip()
                    email = email.split('<')[1].split('>')[0].strip()
                elif '@' in email:
                    # Just email address, use email prefix as name
                    recipient_name = email.split('@')[0]
                
                to_recipients.append(sib_api_v3_sdk.SendSmtpEmailTo(
                    email=email,
                    name=recipient_name
                ))
            
            # Prepare email content
            email_data = sib_api_v3_sdk.SendSmtpEmail(
                sender=sender,
                to=to_recipients,
                subject=message.subject,
                text_content=message.body,
                html_content=self._get_html_content(message)
            )
            
            # Handle attachments
            if hasattr(message, 'attachments') and message.attachments:
                email_data.attachment = self._prepare_attachments(message.attachments)
            
            # Send email
            response = self.api_instance.send_transac_email(email_data)
            
            logger.info(f"Email sent successfully via Brevo. Message ID: {response.message_id}")
            return True
            
        except ApiException as e:
            logger.error(f"Brevo API error: {e}")
            if not self.fail_silently:
                raise
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email via Brevo: {e}")
            if not self.fail_silently:
                raise
            return False

    def _get_html_content(self, message: EmailMessage) -> Optional[str]:
        """
        Extract HTML content from EmailMultiAlternatives if available.
        """
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives:
                if mimetype == 'text/html':
                    return content
        return None

    def _prepare_attachments(self, attachments: List) -> List[sib_api_v3_sdk.SendSmtpEmailAttachment]:
        """
        Convert Django email attachments to Brevo format.
        """
        brevo_attachments = []
        
        for attachment in attachments:
            if len(attachment) >= 3:
                filename, content, mimetype = attachment[:3]
                
                # Convert content to base64 if it's not already
                if isinstance(content, str):
                    import base64
                    content = base64.b64encode(content.encode()).decode()
                elif isinstance(content, bytes):
                    import base64
                    content = base64.b64encode(content).decode()
                
                brevo_attachment = sib_api_v3_sdk.SendSmtpEmailAttachment(
                    content=content,
                    name=filename
                )
                brevo_attachments.append(brevo_attachment)
        
        return brevo_attachments


class BrevoSMTPBackend(BaseEmailBackend):
    """
    Fallback SMTP backend using Brevo SMTP settings.
    This is used when API key is not available.
    """
    
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        
        # Import SMTP backend
        from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
        
        # Configure SMTP settings for Brevo
        smtp_host = getattr(settings, 'BREVO_SMTP_HOST', 'smtp-relay.brevo.com')
        smtp_port = getattr(settings, 'BREVO_SMTP_PORT', 587)
        smtp_user = getattr(settings, 'BREVO_SMTP_USER', '')
        smtp_password = getattr(settings, 'BREVO_SMTP_PASSWORD', '')
        
        self.smtp_backend = SMTPBackend(
            host=smtp_host,
            port=smtp_port,
            username=smtp_user,
            password=smtp_password,
            use_tls=True,
            fail_silently=fail_silently,
            **kwargs
        )

    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        """
        Delegate to SMTP backend.
        """
        return self.smtp_backend.send_messages(email_messages)

    def open(self):
        """Open connection."""
        return self.smtp_backend.open()

    def close(self):
        """Close connection."""
        return self.smtp_backend.close()
