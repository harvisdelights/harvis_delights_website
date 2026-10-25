import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Order, OrderEmail, Payment
from .services import payments
from .admin import OrderAdminForm
from django.core.exceptions import ValidationError


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

    def test_verified_capture_confirms_order_and_queues_one_receipt_pair(self):
        self.user.email = "buyer@example.com"
        self.user.save(update_fields=["email"])
        payment = Payment.objects.create(order=self.order, gateway_order_id="order_123", status=Payment.Status.PENDING)

        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(payments.record_capture("order_123", self.entity))
            self.assertTrue(payments.record_capture("order_123", self.entity))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        receipts = OrderEmail.objects.filter(deduplication_key__startswith=f"payment-captured:{payment.pk}:")
        self.assertEqual(receipts.count(), 2)
        self.assertCountEqual(receipts.values_list("recipient", flat=True), [self.user.email, "hdcare@harvisdelights.com"])

    @patch("store.services.payments.request_api")
    def test_reconcile_recovers_only_matching_unrefunded_capture(self, api):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.TEST, gateway_order_id="order_123", status=Payment.Status.PENDING)
        api.return_value = {"count": 1, "items": [{**self.entity, "amount_refunded": 0}]}
        self.assertTrue(payments.reconcile_pending(payment))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.gateway_payment_id, "pay_123")
        api.assert_called_once_with("GET", "orders/order_123/payments")

    @patch("store.services.payments.request_api")
    def test_reconcile_refund_and_ambiguous_responses_do_not_mark_paid(self, api):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.TEST, gateway_order_id="order_123", status=Payment.Status.PENDING)
        api.return_value = {"count": 1, "items": [{**self.entity, "amount_refunded": 1}]}
        self.assertFalse(payments.reconcile_pending(payment))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVIEW)
        payment.status = Payment.Status.PENDING
        payment.save(update_fields=["status"])
        api.return_value = {"count": 2, "items": [{**self.entity, "amount_refunded": 0}]}
        with self.assertRaises(ValueError):
            payments.reconcile_pending(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @patch("store.services.payments.request_api")
    def test_reconcile_does_not_query_review_or_other_environment(self, api):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.LIVE, gateway_order_id="order_123", status=Payment.Status.PENDING)
        self.assertFalse(payments.reconcile_pending(payment))
        api.assert_not_called()

    def test_late_capture_does_not_overwrite_manual_review(self):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.TEST, gateway_order_id="order_123", status=Payment.Status.REVIEW)
        self.assertFalse(payments.record_capture("order_123", self.entity))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVIEW)

    def test_refunded_capture_does_not_mark_pending_payment_paid(self):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.TEST, gateway_order_id="order_123", status=Payment.Status.PENDING)
        self.assertFalse(payments.record_capture("order_123", {**self.entity, "amount_refunded": 1}))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVIEW)

    @override_settings(RAZORPAY_MODE="live", RAZORPAY_LIVE_ENABLED=True, RAZORPAY_KEY_ID="rzp_live_example")
    @patch("store.services.payments.request_api", return_value={"id": "order_123", "amount": 54900, "currency": "INR"})
    def test_live_start_requires_live_order_and_creates_live_payment(self, api):
        self.assertEqual(self.client.post(self.start).status_code, 409)
        self.order.environment = Order.Environment.LIVE
        self.order.save(update_fields=["environment"])
        self.assertEqual(self.client.post(self.start).status_code, 200)
        self.assertEqual(Payment.objects.get().environment, Payment.Environment.LIVE)

    @patch("store.services.payments.request_api")
    def test_signed_refund_webhook_blocks_late_capture(self, api):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.TEST, gateway_order_id="order_123", gateway_payment_id="pay_123", status=Payment.Status.PAID)
        api.return_value = {**self.entity, "amount_refunded": 100}
        payload = json.dumps({"event": "refund.processed", "payload": {"refund": {"entity": {"payment_id": "pay_123"}}}}).encode()
        signature = hmac.new(b"webhook-secret", payload, hashlib.sha256).hexdigest()
        self.assertEqual(self.client.post(self.webhook, payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature).status_code, 200)
        self.assertFalse(payments.record_capture("order_123", self.entity))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REVIEW)

    def test_live_fulfillment_requires_captured_live_payment(self):
        self.order.environment = Order.Environment.LIVE
        self.order.save(update_fields=["environment"])
        form = OrderAdminForm(instance=self.order)
        form.cleaned_data = {"status": Order.Status.SHIPPED}
        with self.assertRaises(ValidationError):
            form.clean_status()
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.LIVE, status=Payment.Status.PAID)
        self.assertEqual(form.clean_status(), Order.Status.SHIPPED)
        payment.status = Payment.Status.REVIEW
        payment.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            form.clean_status()

    @override_settings(RAZORPAY_MODE="live", RAZORPAY_LIVE_ENABLED=True, RAZORPAY_KEY_ID="rzp_test_example")
    def test_live_mode_rejects_test_keys(self):
        self.assertFalse(payments.configured())

    @patch("store.services.payments.request_api")
    def test_refund_webhook_rejects_bad_signature_without_fetch(self, api):
        payload = json.dumps({"event": "refund.created", "payload": {"refund": {"entity": {"payment_id": "pay_123"}}}}).encode()
        self.assertEqual(self.client.post(self.webhook, payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="bad").status_code, 400)
        api.assert_not_called()

    def test_account_labels_captured_payment_by_environment(self):
        payment = Payment.objects.create(order=self.order, environment=Payment.Environment.LIVE, gateway_order_id="order_123", gateway_payment_id="pay_123", status=Payment.Status.PAID)
        response = self.client.get(reverse("account"))
        self.assertContains(response, "Payment captured")
        self.assertNotContains(response, "Test payment captured")
        payment.environment = Payment.Environment.LEGACY
        payment.save(update_fields=["environment"])
        self.assertContains(self.client.get(reverse("account")), "environment unverified")

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

    def test_checkout_has_no_cash_on_delivery_option(self):
        response = self.client.get(reverse("checkout"))
        self.assertContains(response, "Secure online payment")
        self.assertNotContains(response, "Cash on delivery")

    @override_settings(RAZORPAY_KEY_ID="")
    def test_checkout_does_not_create_an_order_when_online_payment_is_unavailable(self):
        quote = self.client.post(reverse("cart_review"), {"cart_payload": "[]"})
        self.assertEqual(quote.status_code, 400)
        response = self.client.post(reverse("checkout"), {"checkout_id": "not-a-checkout-id"})
        self.assertContains(response, "No order was created")
        self.assertEqual(Order.objects.count(), 1)  # Only self.order from setUp.

    def test_order_page_only_auto_starts_for_active_checkout(self):
        response = self.client.get(reverse("order_confirmation", args=[self.order.number]))
        self.assertContains(response, "sessionStorage.getItem('harvis-checkout-active')")
        self.assertContains(response, "Pay in test mode")
        self.assertNotContains(response, "will confirm your order")
