from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .admin import OrderAdmin
from .models import Order, OrderEmail
from .services.notifications import deliver_order_email, queue_new_order_emails
from .services.zeptomail import ZeptoMailBackend


TEST_STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=TEST_STORAGES, EMAIL_BACKEND="store.services.zeptomail.ZeptoMailBackend", ZEPTOMAIL_API_URL="https://api.zeptomail.com/v1.1/email", ZEPTOMAIL_API_KEY="test-key", PUBLIC_SITE_URL="https://harvisdelights.com", DEFAULT_FROM_EMAIL="hdcare@harvisdelights.com", SELLER_NOTIFICATION_EMAIL="hdcare@harvisdelights.com")
class EmailIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="buyer@example.com", email="buyer@example.com", password="OldPassword28!")
        self.order = Order.objects.create(user=self.user, subtotal=Decimal("100.00"), total=Decimal("100.00"))

    @patch("store.services.zeptomail.requests.post")
    def test_zeptomail_sends_https_payload(self, post):
        post.return_value = Mock(status_code=201)
        sent = ZeptoMailBackend().send_messages([EmailMessage("Subject", "Hello", "hdcare@harvisdelights.com", ["buyer@example.com"])])
        self.assertEqual(sent, 1)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Zoho-enczapikey test-key")
        self.assertEqual(post.call_args.kwargs["json"]["to"][0]["email_address"]["address"], "buyer@example.com")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @override_settings(ZEPTOMAIL_API_URL="https://cpaas.zoho.in/v1.1/email")
    @patch("store.services.zeptomail.requests.post")
    def test_cpaas_india_send_endpoint_is_allowed(self, post):
        post.return_value = Mock(status_code=201)

        sent = ZeptoMailBackend().send_messages([
            EmailMessage("Subject", "Hello", "hdcare@harvisdelights.com", ["buyer@example.com"])
        ])

        self.assertEqual(sent, 1)
        self.assertEqual(post.call_args.args[0], "https://cpaas.zoho.in/v1.1/email")

    @override_settings(ZEPTOMAIL_API_URL="https://evil.example/v1.1/email")
    @patch("store.services.zeptomail.requests.post")
    def test_key_not_sent_to_untrusted_url(self, post):
        with self.assertRaises(RuntimeError):
            ZeptoMailBackend().send_messages([EmailMessage("Subject", "Hello", "hdcare@harvisdelights.com", ["buyer@example.com"])])
        post.assert_not_called()

    @patch("store.services.zeptomail.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_failure_is_recorded_and_can_be_retried(self, post):
        with self.captureOnCommitCallbacks(execute=True):
            queue_new_order_emails(self.order)
        self.assertEqual(OrderEmail.objects.filter(status="failed").count(), 2)
        notification = OrderEmail.objects.first()
        post.side_effect = None
        post.return_value = Mock(status_code=201)
        deliver_order_email(notification.pk)
        notification.refresh_from_db()
        self.assertEqual(notification.status, "sent")
        self.assertEqual(notification.attempts, 2)
        deliver_order_email(notification.pk)
        self.assertEqual(post.call_count, 3)

    @override_settings(ZEPTOMAIL_API_KEY="")
    def test_unconfigured_notifications_stay_pending(self):
        with self.captureOnCommitCallbacks(execute=True):
            queue_new_order_emails(self.order)
        self.assertEqual(OrderEmail.objects.filter(status="pending").count(), 2)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_status_change_sends_once_but_unchanged_save_does_not(self):
        manager = OrderAdmin(Order, admin.site)
        self.order.status = "confirmed"
        with self.captureOnCommitCallbacks(execute=True):
            manager.save_model(None, self.order, SimpleNamespace(changed_data=["status"]), True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Confirmed", mail.outbox[0].subject)
        with self.captureOnCommitCallbacks(execute=True):
            manager.save_model(None, self.order, SimpleNamespace(changed_data=[]), True)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_uses_configured_origin_and_updates_password(self):
        response = self.client.post(reverse("password_recovery"), {"email": self.user.email}, HTTP_HOST="testserver")
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("https://"))
        self.assertTrue(link.startswith("https://harvisdelights.com/password-reset/"))
        path = link.removeprefix("https://harvisdelights.com")
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response.url, {"new_password1": "NewStrongPass99!", "new_password2": "NewStrongPass99!"})
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass99!"))

    @override_settings(ZEPTOMAIL_API_KEY="")
    def test_password_recovery_is_disabled_without_provider(self):
        self.assertContains(self.client.get(reverse("password_recovery")), "being set up")

    @patch("store.management.commands.send_test_email.send_mail", return_value=1)
    def test_send_test_email_command_uses_explicit_recipient(self, send_mail):
        output = StringIO()

        call_command("send_test_email", "--to", "owner@example.com", stdout=output)

        self.assertIn("accepted one test email", output.getvalue())
        self.assertEqual(send_mail.call_args.args[3], ["owner@example.com"])

    @override_settings(ZEPTOMAIL_API_KEY="")
    def test_send_test_email_command_requires_provider_configuration(self):
        with self.assertRaises(CommandError):
            call_command("send_test_email", "--to", "owner@example.com")
