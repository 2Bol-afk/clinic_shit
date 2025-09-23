from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import transaction


class Command(BaseCommand):
    help = "Delete all application data except Django superusers and auth essentials. Irreversible."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Run non-interactively without confirmation",
        )

    def handle(self, *args, **options):
        non_interactive = options.get("yes")

        if not non_interactive:
            confirm = input(
                "This will DELETE ALL DATA except superusers. Type 'DELETE' to continue: "
            )
            if confirm.strip().upper() != "DELETE":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        from django.apps import apps

        # Always preserve superusers
        superuser_ids = list(User.objects.filter(is_superuser=True).values_list("id", flat=True))

        # Models to skip (auth and sessions + contenttypes are safe to clear by app logic elsewhere)
        skip_models = set(
            [
                ("auth", "User"),
                ("auth", "Group"),
                ("auth", "Permission"),
                ("contenttypes", "ContentType"),
                ("sessions", "Session"),
                ("admin", "LogEntry"),
            ]
        )

        # Purge non-superuser users explicitly (keep superusers)
        with transaction.atomic():
            User.objects.exclude(id__in=superuser_ids).delete()

        # Iterate all models and delete data
        with transaction.atomic():
            for model in apps.get_models():
                app_label = model._meta.app_label
                model_name = model.__name__
                if (app_label, model_name) in skip_models:
                    continue
                # Skip unmanaged or proxy models
                if getattr(model._meta, "managed", True) is False or getattr(model._meta, "proxy", False):
                    continue
                try:
                    # Special handling: for User model already handled
                    if model is User:
                        continue
                    count = model.objects.all().count()
                    if count:
                        model.objects.all().delete()
                        self.stdout.write(
                            self.style.SUCCESS(f"Cleared {count} {app_label}.{model_name} records")
                        )
                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(f"Skip {app_label}.{model_name}: {exc}")
                    )

        self.stdout.write(self.style.SUCCESS("Purge complete. Superusers preserved."))


