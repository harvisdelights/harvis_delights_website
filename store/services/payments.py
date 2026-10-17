import hashlib
import hmac

import requests
from django.conf import settings
from django.db import transaction

from store.models import Payment


def configured():
    # Deliberately refuse live keys until a production payment review is complete.
    return bool(settings.RAZORPAY_KEY_ID.startswith("rzp_test_") and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_WEBHOOK_SECRET)


def signature_valid(message, signature, secret):
    if not isinstance(signature, str):
        return False
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def request_api(method, path, **kwargs):
    response = requests.request(method, "https://api.razorpay.com/v1/" + path,
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET), timeout=10, **kwargs)
    response.raise_for_status()
    return response.json()


def record_capture(gateway_order_id, entity):
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("order").filter(gateway_order_id=gateway_order_id).first()
        if not payment:
            return False
        expected_amount = int(payment.order.total * 100)
        payment_id = entity.get("id")
        if (entity.get("order_id") != gateway_order_id or entity.get("status") != "captured"
                or entity.get("currency") != "INR" or entity.get("amount") != expected_amount
                or not isinstance(payment_id, str) or not payment_id.startswith("pay_") or len(payment_id) > 100):
            return False
        if payment.status == Payment.Status.PAID:
            return payment.gateway_payment_id == payment_id
        payment.gateway_payment_id = payment_id
        payment.status = Payment.Status.PAID
        payment.save(update_fields=["gateway_payment_id", "status", "updated_at"])
        return True
