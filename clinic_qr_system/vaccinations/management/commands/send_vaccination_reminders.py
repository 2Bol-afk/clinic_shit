from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from vaccinations.models import VaccineDose, VaccinationReminder
from vaccinations.views import send_vaccination_reminder_email


class Command(BaseCommand):
    help = 'Send vaccination reminders for due doses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=1,
            help='Number of days ahead to send reminders (default: 1)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending emails'
        )

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        dry_run = options['dry_run']
        
        # Calculate the target date
        target_date = timezone.now().date() + timedelta(days=days_ahead)
        
        # Find doses that need reminders
        doses_needing_reminders = VaccineDose.objects.filter(
            administered=False,
            scheduled_date=target_date
        ).select_related('vaccination__patient', 'vaccination__vaccine_type')
        
        if not doses_needing_reminders.exists():
            self.stdout.write(
                self.style.WARNING(f'No doses scheduled for {target_date}')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Found {doses_needing_reminders.count()} doses scheduled for {target_date}')
        )
        
        sent_count = 0
        failed_count = 0
        
        for dose in doses_needing_reminders:
            patient = dose.vaccination.patient
            vaccine_name = dose.vaccination.vaccine_type.name
            
            # Check if reminder already sent
            existing_reminder = VaccinationReminder.objects.filter(
                dose=dose,
                sent=True
            ).first()
            
            if existing_reminder:
                self.stdout.write(
                    self.style.WARNING(
                        f'Reminder already sent for {patient.full_name} - {vaccine_name} Dose {dose.dose_number}'
                    )
                )
                continue
            
            if dry_run:
                self.stdout.write(
                    f'Would send reminder to {patient.full_name} ({patient.email}) '
                    f'for {vaccine_name} Dose {dose.dose_number}'
                )
                sent_count += 1
            else:
                try:
                    # Send the reminder email
                    if send_vaccination_reminder_email(dose):
                        sent_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Reminder sent to {patient.full_name} for {vaccine_name} Dose {dose.dose_number}'
                            )
                        )
                    else:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'Failed to send reminder to {patient.full_name} for {vaccine_name} Dose {dose.dose_number}'
                            )
                        )
                except Exception as e:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'Error sending reminder to {patient.full_name}: {str(e)}'
                        )
                    )
        
        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'DRY RUN: Would send {sent_count} reminders for doses scheduled on {target_date}'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully sent {sent_count} reminders. Failed: {failed_count}'
                )
            )