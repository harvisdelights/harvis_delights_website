"""Send one explicit, operator-requested ZeptoMail delivery check."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from store.services.zeptomail import email_configured


class Command(BaseCommand):
    help = "Send a single ZeptoMail configuration test to the supplied recipient."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Recipient address for this one test email.")

    def handle(self, *args, **options):
        recipient = options["to"].strip()
        try:
            validate_email(recipient)
        except ValidationError as exc:
            raise CommandError("--to must be a valid email address.") from exc

        if not email_configured():
            raise CommandError("ZeptoMail is not configured. Set ZEPTOMAIL_API_URL and ZEPTOMAIL_API_KEY first.")

        subject = "Harvi's Delights email delivery check"
        body = (
            "This is a manually requested transactional-email delivery check. "
            "No order was created and no payment was affected."
        )
        try:
            accepted = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
        except Exception as exc:
            raise CommandError("ZeptoMail did not accept the test email. Check Render and ZeptoMail logs.") from exc

        if accepted != 1:
            raise CommandError("ZeptoMail did not accept the test email.")
        self.stdout.write(self.style.SUCCESS("ZeptoMail accepted one test email. Check the recipient inbox and ZeptoMail logs."))
