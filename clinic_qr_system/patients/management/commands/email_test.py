from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings


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

        if not getattr(settings, 'EMAIL_BACKEND', ''):
            raise CommandError('EMAIL_BACKEND is not configured.')

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        sent = send_mail(
            subject,
            message,
            from_email,
            [recipient],
            fail_silently=False,
        )

        if sent:
            self.stdout.write(self.style.SUCCESS(f'Sent test email to {recipient}'))
        else:
            raise CommandError('send_mail returned 0 (no emails sent).')


