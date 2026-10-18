import hashlib
import hmac
import re

import requests
from django.conf import settings
from django.db import transaction

from store.models import Payment


def configured():
    mode = settings.RAZORPAY_MODE
    # Real-money processing remains blocked until reconciliation and refunds are verified.
    if mode != "test":
        return False
    return bool(settings.RAZORPAY_KEY_ID.startswith(f"rzp_{mode}_") and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_WEBHOOK_SECRET)


def compatible(payment):
    # Legacy records remain usable only in test mode; never assume they are live.
    return payment.environment == settings.RAZORPAY_MODE or (settings.RAZORPAY_MODE == "test" and payment.environment == Payment.Environment.LEGACY)


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
        if not payment or not configured() or not compatible(payment):
            return False
        expected_amount = int(payment.order.total * 100)
        payment_id = entity.get("id")
        if (entity.get("order_id") != gateway_order_id or entity.get("status") != "captured"
                or entity.get("currency") != "INR" or entity.get("amount") != expected_amount
                or not isinstance(payment_id, str) or not payment_id.startswith("pay_") or len(payment_id) > 100):
            return False
        if payment.status == Payment.Status.PAID:
            return payment.gateway_payment_id == payment_id
        # Never overwrite a manual-review decision with a late gateway event.
        if payment.status != Payment.Status.PENDING or entity.get("amount_refunded", 0) != 0:
            return False
        payment.gateway_payment_id = payment_id
        payment.status = Payment.Status.PAID
        payment.save(update_fields=["gateway_payment_id", "status", "updated_at"])
        return True


def reconcile_pending(payment):
    """Recover a missing capture from Razorpay; never create or retry a charge."""
    if (not configured() or not compatible(payment) or payment.status != Payment.Status.PENDING
            or not re.fullmatch(r"order_[A-Za-z0-9]{1,94}", payment.gateway_order_id or "")):
        return False
    result = request_api("GET", f"orders/{payment.gateway_order_id}/payments")
    if (not isinstance(result, dict) or not isinstance(result.get("items"), list)
            or result.get("count") != len(result["items"])):
        raise ValueError("Invalid gateway response")
    items = result["items"]
    captured = [item for item in items if isinstance(item, dict) and item.get("status") == "captured"]
    # Ambiguity, refunds and unexpected data require a manual investigation.
    if len(captured) != 1 or captured[0].get("amount_refunded") != 0:
        return False
    return record_capture(payment.gateway_order_id, captured[0])
