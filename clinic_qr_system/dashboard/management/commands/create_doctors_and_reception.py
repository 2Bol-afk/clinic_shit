from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils.crypto import get_random_string
from django.db import transaction


class Command(BaseCommand):
    help = "Create one doctor per department and one reception account; write credentials to details.txt"

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Run non-interactively")
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Force-reset doctor passwords to their department value",
        )

    def handle(self, *args, **options):
        from patients.models import DEPARTMENT_CHOICES, Doctor
        created_rows = []
        reset = bool(options.get("reset"))

        def ensure_group(name: str) -> Group:
            g, _ = Group.objects.get_or_create(name=name)
            return g

        doctor_group = ensure_group('Doctor')
        reception_group = ensure_group('Reception')

        def gen_password() -> str:
            return get_random_string(12)

        with transaction.atomic():
            # Create Reception account
            rec_username = 'reception_account'
            rec_user, created = User.objects.get_or_create(
                username=rec_username,
                defaults={
                    'email': 'reception@clinic.local',
                    'first_name': 'Reception',
                    'last_name': 'Account',
                    'is_active': True,
                }
            )
            rec_password = None
            if created or not rec_user.has_usable_password():
                rec_password = gen_password()
                rec_user.set_password(rec_password)
                rec_user.save()
            rec_user.groups.add(reception_group)
            if rec_password:
                created_rows.append((rec_username, rec_password, 'Reception'))

            # Create one doctor per department
            for dept_value, dept_label in DEPARTMENT_CHOICES:
                base_username = f"doctor_{dept_value.lower()}"
                user, created = User.objects.get_or_create(
                    username=base_username,
                    defaults={
                        'email': f'{base_username}@clinic.local',
                        'first_name': 'Doctor',
                        'last_name': dept_label,
                        'is_active': True,
                    }
                )
                password = None
                # If resetting, set password to department value exactly
                if reset:
                    password = dept_value
                    user.set_password(password)
                    user.save(update_fields=['password'])
                elif created or not user.has_usable_password():
                    password = gen_password()
                    user.set_password(password)
                    user.save()
                user.groups.add(doctor_group)

                # Ensure Doctor profile exists
                Doctor.objects.get_or_create(
                    user=user,
                    defaults={
                        'full_name': f'Dr. {dept_label}',
                        'specialization': dept_value,
                    }
                )
                if password:
                    created_rows.append((base_username, password, f'Doctor - {dept_label}'))

        # Write to details.txt at project root
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        details_path = os.path.join(project_root, 'details.txt')
        with open(details_path, 'a', encoding='utf-8') as f:
            f.write('\n# Created doctor & reception accounts\n')
            for username, password, role in created_rows:
                f.write(f"{role}: {username} | {password}\n")

        self.stdout.write(self.style.SUCCESS(f"Created/ensured {len(created_rows)} accounts. Credentials appended to details.txt"))


