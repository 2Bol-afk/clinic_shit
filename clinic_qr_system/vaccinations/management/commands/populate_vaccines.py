from django.core.management.base import BaseCommand
from vaccinations.models import VaccineType


class Command(BaseCommand):
    help = 'Populate the database with common vaccine types'

    def handle(self, *args, **options):
        vaccine_data = [
            {
                'name': 'COVID-19 Vaccine (mRNA)',
                'description': 'COVID-19 vaccine using mRNA technology (Pfizer-BioNTech or Moderna)',
                'total_doses_required': 2,
                'dose_intervals': [0, 21],  # 0 days, 21 days (3 weeks)
                'age_minimum': 72,  # 6 months
                'age_maximum': None,
            },
            {
                'name': 'COVID-19 Vaccine (J&J)',
                'description': 'COVID-19 vaccine using viral vector technology (Johnson & Johnson)',
                'total_doses_required': 1,
                'dose_intervals': [0],
                'age_minimum': 216,  # 18 years
                'age_maximum': None,
            },
            {
                'name': 'Influenza (Flu) Vaccine',
                'description': 'Annual influenza vaccine for seasonal flu protection',
                'total_doses_required': 1,
                'dose_intervals': [0],
                'age_minimum': 6,  # 6 months
                'age_maximum': None,
            },
            {
                'name': 'Influenza (Flu) Vaccine - First Time Children',
                'description': 'Influenza vaccine for children receiving it for the first time',
                'total_doses_required': 2,
                'dose_intervals': [0, 28],  # 0 days, 28 days (4 weeks)
                'age_minimum': 6,  # 6 months
                'age_maximum': 216,  # 18 years
            },
            {
                'name': 'Hepatitis B Vaccine',
                'description': 'Hepatitis B vaccine for protection against hepatitis B virus',
                'total_doses_required': 3,
                'dose_intervals': [0, 30, 180],  # 0 days, 1 month, 6 months
                'age_minimum': 0,  # Birth
                'age_maximum': None,
            },
            {
                'name': 'Tetanus Vaccine',
                'description': 'Tetanus vaccine for protection against tetanus (lockjaw)',
                'total_doses_required': 5,
                'dose_intervals': [0, 30, 60, 90, 3650],  # 0, 1 month, 2 months, 3 months, 10 years
                'age_minimum': 6,  # 6 months
                'age_maximum': None,
            },
            {
                'name': 'MMR Vaccine',
                'description': 'Measles, Mumps, and Rubella combined vaccine',
                'total_doses_required': 2,
                'dose_intervals': [0, 1095],  # 0 days, 3 years (36 months)
                'age_minimum': 12,  # 12 months
                'age_maximum': None,
            },
            {
                'name': 'Polio Vaccine',
                'description': 'Polio vaccine for protection against poliomyelitis',
                'total_doses_required': 4,
                'dose_intervals': [0, 60, 120, 1095],  # 0, 2 months, 4 months, 3 years
                'age_minimum': 2,  # 2 months
                'age_maximum': None,
            },
            {
                'name': 'Varicella (Chickenpox) Vaccine',
                'description': 'Varicella vaccine for protection against chickenpox',
                'total_doses_required': 2,
                'dose_intervals': [0, 1095],  # 0 days, 3 years (36 months)
                'age_minimum': 12,  # 12 months
                'age_maximum': None,
            },
            {
                'name': 'HPV Vaccine (2-dose schedule)',
                'description': 'Human Papillomavirus vaccine for ages 9-14 (2 doses)',
                'total_doses_required': 2,
                'dose_intervals': [0, 180],  # 0 days, 6 months
                'age_minimum': 108,  # 9 years
                'age_maximum': 180,  # 15 years
            },
            {
                'name': 'HPV Vaccine (3-dose schedule)',
                'description': 'Human Papillomavirus vaccine for ages 15+ (3 doses)',
                'total_doses_required': 3,
                'dose_intervals': [0, 60, 180],  # 0 days, 2 months, 6 months
                'age_minimum': 180,  # 15 years
                'age_maximum': None,
            },
        ]

        created_count = 0
        updated_count = 0

        for vaccine_info in vaccine_data:
            vaccine_type, created = VaccineType.objects.get_or_create(
                name=vaccine_info['name'],
                defaults=vaccine_info
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created vaccine type: {vaccine_type.name}')
                )
            else:
                # Update existing vaccine type
                for key, value in vaccine_info.items():
                    setattr(vaccine_type, key, value)
                vaccine_type.save()
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated vaccine type: {vaccine_type.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nVaccine population completed!\n'
                f'Created: {created_count} vaccine types\n'
                f'Updated: {updated_count} vaccine types\n'
                f'Total: {VaccineType.objects.count()} vaccine types in database'
            )
        )
