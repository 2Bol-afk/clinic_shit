from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings
from clinic_qr_system.email_utils import send_test_email, get_email_provider_info


class Command(BaseCommand):
    help = 'Send a test email using current Django email settings.'

    def add_arguments(self, parser):
        parser.add_argument('--to', required=True, help='Recipient email address')
        parser.add_argument('--subject', default='Clinic QR System Test Email')
        parser.add_argument('--message', default='This is a test email from Clinic QR System.')

    def handle(self, *args, **options):
        recipient = options['to']
        subject = options['subject']
        message = options['message']

        # Get email provider info
        provider_info = get_email_provider_info()
        provider_name = provider_info.get('provider', 'unknown').upper()
        
        self.stdout.write(f"Email Provider: {provider_name}")
        self.stdout.write(f"Email Backend: {provider_info.get('backend', 'unknown')}")
        self.stdout.write(f"From Email: {provider_info.get('from_email', 'unknown')}")
        
        if provider_name == 'BREVO':
            if provider_info.get('api_key_configured'):
                self.stdout.write("Using Brevo API backend")
            else:
                self.stdout.write("Using Brevo SMTP backend")
            self.stdout.write(f"Sender: {provider_info.get('sender_name', 'unknown')} <{provider_info.get('sender_email', 'unknown')}>")

        try:
            sent = send_test_email(
                recipient_email=recipient,
                message=message,
                subject=subject
            )

            if sent:
                self.stdout.write(self.style.SUCCESS(f'Sent test email to {recipient} via {provider_name}'))
            else:
                raise CommandError('send_test_email returned False (no emails sent).')
        except Exception as e:
            raise CommandError(f'Email sending failed: {e}')


