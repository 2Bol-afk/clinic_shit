from django.core.management.base import BaseCommand
from vaccinations.models import VaccineType


class Command(BaseCommand):
    help = 'Populate vaccine types with standard vaccination data'

    def handle(self, *args, **options):
        vaccine_data = [
            {
                'name': 'COVID-19',
                'description': 'COVID-19 vaccine with optional booster',
                'total_doses_required': 2,
                'dose_intervals': [0, 28],  # 0 days, 28 days (4 weeks)
            },
            {
                'name': 'Influenza',
                'description': 'Annual influenza vaccine',
                'total_doses_required': 1,
                'dose_intervals': [0],
            },
            {
                'name': 'Hepatitis B',
                'description': 'Hepatitis B vaccine series',
                'total_doses_required': 3,
                'dose_intervals': [0, 30, 180],  # 0 days, 1 month, 6 months
            },
            {
                'name': 'Tetanus (Tdap)',
                'description': 'Tetanus, Diphtheria, and Pertussis vaccine with booster every 10 years',
                'total_doses_required': 1,
                'dose_intervals': [0],
            },
            {
                'name': 'MMR (Measles, Mumps, Rubella)',
                'description': 'Measles, Mumps, and Rubella vaccine',
                'total_doses_required': 2,
                'dose_intervals': [0, 28],  # 0 days, 4 weeks
            },
            {
                'name': 'Chickenpox (Varicella)',
                'description': 'Varicella (Chickenpox) vaccine',
                'total_doses_required': 2,
                'dose_intervals': [0, 90],  # 0 days, 3 months
            },
            {
                'name': 'HPV',
                'description': 'Human Papillomavirus vaccine (2-3 doses depending on age)',
                'total_doses_required': 3,
                'dose_intervals': [0, 60, 180],  # 0 days, 2 months, 6 months
            },
            {
                'name': 'Polio (IPV)',
                'description': 'Inactivated Poliovirus vaccine',
                'total_doses_required': 4,
                'dose_intervals': [0, 30, 60, 365],  # 0 days, 1 month, 2 months, 1 year
            },
            {
                'name': 'DPT (Diphtheria, Pertussis, Tetanus)',
                'description': 'Diphtheria, Pertussis, and Tetanus vaccine with boosters',
                'total_doses_required': 5,
                'dose_intervals': [0, 30, 60, 90, 365],  # 0 days, 1 month, 2 months, 3 months, 1 year
            },
            {
                'name': 'Typhoid',
                'description': 'Typhoid vaccine (repeat every 2-3 years if required)',
                'total_doses_required': 1,
                'dose_intervals': [0],
            },
        ]

        created_count = 0
        updated_count = 0

        for vaccine_info in vaccine_data:
            vaccine_type, created = VaccineType.objects.get_or_create(
                name=vaccine_info['name'],
                defaults={
                    'description': vaccine_info['description'],
                    'total_doses_required': vaccine_info['total_doses_required'],
                    'dose_intervals': vaccine_info['dose_intervals'],
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created vaccine type: {vaccine_type.name}')
                )
            else:
                # Update existing vaccine type
                vaccine_type.description = vaccine_info['description']
                vaccine_type.total_doses_required = vaccine_info['total_doses_required']
                vaccine_type.dose_intervals = vaccine_info['dose_intervals']
                vaccine_type.is_active = True
                vaccine_type.save()
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated vaccine type: {vaccine_type.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {len(vaccine_data)} vaccine types. '
                f'Created: {created_count}, Updated: {updated_count}'
            )
        )
