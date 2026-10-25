import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from store.models import OrderEmail
from .zeptomail import email_configured

logger = logging.getLogger(__name__)


def deliver_order_email(notification_id):
    if not email_configured():
        return
    claimed = OrderEmail.objects.filter(pk=notification_id, status__in=[OrderEmail.Status.PENDING, OrderEmail.Status.FAILED]).update(status=OrderEmail.Status.SENDING, attempts=F("attempts") + 1, last_error="")
    if not claimed:
        return
    notification = OrderEmail.objects.get(pk=notification_id)
    try:
        send_mail(notification.subject, notification.body, settings.DEFAULT_FROM_EMAIL, [notification.recipient], fail_silently=False)
    except Exception:
        logger.warning("Order email %s could not be accepted by the provider", notification_id)
        OrderEmail.objects.filter(pk=notification_id).update(status=OrderEmail.Status.FAILED, last_error="Email service unavailable or rejected the message. Check Render and ZeptoMail logs.")
    else:
        OrderEmail.objects.filter(pk=notification_id).update(status=OrderEmail.Status.SENT, sent_at=timezone.now())


def queue_order_email(order, recipient, subject, body, *, deduplication_key=None):
    if not recipient:
        return
    if deduplication_key:
        notification, created = OrderEmail.objects.get_or_create(
            deduplication_key=deduplication_key,
            defaults={"order": order, "recipient": recipient, "subject": subject, "body": body},
        )
        if not created:
            return
    else:
        notification = OrderEmail.objects.create(order=order, recipient=recipient, subject=subject, body=body)
    transaction.on_commit(lambda: deliver_order_email(notification.pk), robust=True)


def queue_new_order_emails(order):
    lines = "\n".join(f"- {item.product_name} x {item.quantity}: INR {item.unit_price} each" for item in order.items.all())
    body = f"Order reference: {order.number}\nOrder status: {order.get_status_display()}\nPayment status: Not paid at time of order creation\n\n{lines}\n\nItems subtotal: INR {order.total}\nDelivery is free. Check the order page for the latest payment status.\n\nHarvi's Delights"
    queue_order_email(order, order.user.email, f"Order received - {order.number}", f"Thank you. Your order has been received; payment is separate.\n\n{body}")
    queue_order_email(order, settings.SELLER_NOTIFICATION_EMAIL, f"New order - {order.number}", f"A customer placed an order. Verify payment status before dispatch.\n\n{body}")


def queue_payment_captured_emails(payment_id):
    """Queue one customer receipt and one seller alert for a verified capture.

    This is called after the capture transaction commits. It deliberately does
    not run for checkout creation, browser-only success, refunds, or records
    that need manual review.
    """
    from store.models import Payment

    payment = Payment.objects.select_related("order__user").prefetch_related("order__items").filter(pk=payment_id).first()
    if not payment or payment.status != Payment.Status.PAID or not payment.gateway_payment_id:
        return

    order = payment.order
    lines = "\n".join(f"- {item.product_name} x {item.quantity}: INR {item.unit_price} each" for item in order.items.all())
    if payment.environment == Payment.Environment.LIVE:
        customer_intro = "Your payment has been captured successfully."
        seller_intro = "A live payment has been captured."
    else:
        customer_intro = "Your test payment has been captured. No real money was charged."
        seller_intro = "A test payment has been captured. No real money was charged."

    details = f"Order reference: {order.number}\nPayment status: Captured\nAmount paid: INR {order.total}\n\n{lines}\n\nHarvi's Delights"
    queue_order_email(
        order,
        order.user.email,
        f"Payment captured - {order.number}",
        f"Thank you. {customer_intro}\n\n{details}",
        deduplication_key=f"payment-captured:{payment.pk}:customer",
    )
    queue_order_email(
        order,
        settings.SELLER_NOTIFICATION_EMAIL,
        f"Payment captured - {order.number}",
        f"{seller_intro} Do not dispatch until you have checked Razorpay for refunds or disputes.\n\n{details}",
        deduplication_key=f"payment-captured:{payment.pk}:seller",
    )


def queue_order_status_email(order):
    if order.status not in ("confirmed", "shipped", "cancelled"):
        return
    label = order.get_status_display()
    queue_order_email(order, order.user.email, f"Order {order.number}: {label}", f"Your order {order.number} is now marked {label}. Contact {settings.CUSTOMER_SUPPORT_EMAIL} if you have questions.\n\nHarvi's Delights")
