"""Create the initial seller account from deployment environment variables."""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Creates the configured seller superuser if it does not already exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not any((username, email, password)):
            self.stdout.write("No seller bootstrap variables set; skipping superuser creation.")
            return
        if not all((username, email, password)):
            raise CommandError(
                "Set DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, and "
                "DJANGO_SUPERUSER_PASSWORD together."
            )

        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write("Seller superuser already exists; skipping creation.")
            return

        user_model.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS("Seller superuser created."))
