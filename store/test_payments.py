import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Order, Payment


@override_settings(RAZORPAY_KEY_ID="rzp_test_example", RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="webhook-secret", STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PaymentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="buyer", password="password")
        self.client.force_login(self.user)
        self.order = Order.objects.create(user=self.user, subtotal=Decimal("549.00"), total=Decimal("549.00"))
        self.start = reverse("payment_start", args=[self.order.number])
        self.verify = reverse("payment_verify", args=[self.order.number])
        self.webhook = reverse("razorpay_webhook")
        self.entity = {"id": "pay_123", "order_id": "order_123", "amount": 54900, "currency": "INR", "status": "captured"}

    @patch("store.services.payments.request_api", return_value={"id": "order_123", "amount": 54900, "currency": "INR"})
    def test_start_reuses_single_gateway_order(self, api):
        self.assertEqual(self.client.post(self.start).json()["order_id"], "order_123")
        self.assertEqual(self.client.post(self.start).json()["order_id"], "order_123")
        self.assertEqual(api.call_count, 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.get().environment, Payment.Environment.TEST)

    def test_existing_payment_environment_remains_unverified(self):
        payment = Payment.objects.create(order=self.order, gateway_order_id="order_123", status=Payment.Status.PENDING)
        self.assertEqual(self.client.post(self.start).status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.environment, Payment.Environment.LEGACY)

    @patch("store.services.payments.request_api", side_effect=requests.Timeout())
    def test_uncertain_creation_never_retries_automatically(self, api):
        self.assertEqual(self.client.post(self.start).status_code, 503)
        self.assertEqual(self.client.post(self.start).status_code, 503)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(Payment.objects.get().status, Payment.Status.REVIEW)

    @override_settings(RAZORPAY_KEY_ID="rzp_live_example")
    def test_live_keys_disabled(self):
        self.assertEqual(self.client.post(self.start).status_code, 503)
        self.assertFalse(Payment.objects.exists())

    @override_settings(RAZORPAY_MODE="live", RAZORPAY_KEY_ID="rzp_live_example")
    def test_live_mode_remains_disabled(self):
        self.assertEqual(self.client.post(self.start).status_code, 503)
        self.assertFalse(Payment.objects.exists())

    @override_settings(RAZORPAY_MODE="invalid")
    def test_invalid_mode_remains_disabled(self):
        self.assertEqual(self.client.post(self.start).status_code, 503)

    def test_payment_from_other_environment_cannot_be_reused(self):
        Payment.objects.create(order=self.order, environment=Payment.Environment.LIVE, gateway_order_id="order_123", status=Payment.Status.PENDING)
        self.assertEqual(self.client.post(self.start).status_code, 409)

    @patch("store.services.payments.request_api")
    def test_verify_requires_signature_and_captured_amount(self, api):
        Payment.objects.create(order=self.order, gateway_order_id="order_123", status=Payment.Status.PENDING)
        data = {"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_123", "razorpay_signature": "invalid"}
        self.assertEqual(self.client.post(self.verify, data).status_code, 400)
        api.assert_not_called()
        data["razorpay_signature"] = hmac.new(b"secret", b"order_123|pay_123", hashlib.sha256).hexdigest()
        api.return_value = {**self.entity, "amount": 1}
        self.assertEqual(self.client.post(self.verify, data).status_code, 202)
        api.return_value = self.entity
        self.assertTrue(self.client.post(self.verify, data).json()["paid"])
        self.assertEqual(Payment.objects.get().status, Payment.Status.PAID)

    def test_webhook_signature_and_idempotency(self):
        Payment.objects.create(order=self.order, gateway_order_id="order_123", status=Payment.Status.PENDING)
        payload = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": self.entity}}}).encode()
        self.assertEqual(self.client.post(self.webhook, payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="bad").status_code, 400)
        signature = hmac.new(b"webhook-secret", payload, hashlib.sha256).hexdigest()
        for _ in range(2):
            self.assertEqual(self.client.post(self.webhook, payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature).status_code, 200)
        self.assertEqual(Payment.objects.get().status, Payment.Status.PAID)

    def test_other_customer_cannot_start_payment(self):
        other = get_user_model().objects.create_user(username="other")
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.start).status_code, 404)

    def test_minimum_order_amount(self):
        self.order.total = Decimal("0.99")
        self.order.save(update_fields=["total"])
        self.assertEqual(self.client.post(self.start).status_code, 400)
        self.assertFalse(Payment.objects.exists())

    def test_missing_verification_fields_rejected(self):
        Payment.objects.create(order=self.order, gateway_order_id="order_123", status=Payment.Status.PENDING)
        self.assertEqual(self.client.post(self.verify, {}).status_code, 400)
        self.assertEqual(Payment.objects.get().status, Payment.Status.PENDING)

    def test_cod_not_available(self):
        self.assertContains(self.client.get(reverse("checkout")), "Cash on delivery is not available yet")

    def test_order_page_only_auto_starts_for_active_checkout(self):
        response = self.client.get(reverse("order_confirmation", args=[self.order.number]))
        self.assertContains(response, "sessionStorage.getItem('harvis-checkout-active')")
        self.assertContains(response, "Pay in test mode")
        self.assertNotContains(response, "will confirm your order")
