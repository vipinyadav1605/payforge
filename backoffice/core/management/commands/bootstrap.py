from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "First-run setup: create the 'backoffice' schema, migrate Django's own tables, ensure a staff user."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS backoffice")
        call_command("migrate", interactive=False, verbosity=0)

        User = get_user_model()
        username = settings.BACKOFFICE_ADMIN_USER
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username, "", settings.BACKOFFICE_ADMIN_PASSWORD)
            self.stdout.write(self.style.SUCCESS(f"Created staff superuser '{username}'"))
        self.stdout.write(self.style.SUCCESS("Back-office ready"))
