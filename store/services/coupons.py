from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from store.models import Coupon, CouponRedemption, Payment


class CouponError(ValueError):
    pass


def normalise_code(value):
    return (value or "").strip().upper()


def discount_for(coupon, subtotal):
    if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
        discount = (subtotal * coupon.discount_value / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        discount = coupon.discount_value
    if coupon.maximum_discount is not None:
        discount = min(discount, coupon.maximum_discount)
    return min(discount, subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_coupon_for_checkout(*, code, user, subtotal):
    """Return the coupon and calculated discount, or raise a safe customer error."""
    code = normalise_code(code)
    if not code:
        return None, Decimal("0.00")
    coupon = Coupon.objects.filter(code=code).first()
    now = timezone.now()
    if not coupon or not coupon.is_active or (coupon.starts_at and coupon.starts_at > now) or (coupon.expires_at and coupon.expires_at <= now):
        raise CouponError("This coupon is unavailable.")
    if subtotal < coupon.minimum_order_value:
        raise CouponError(f"{coupon.code} requires an items subtotal of at least INR {coupon.minimum_order_value:.2f}.")
    if CouponRedemption.objects.filter(coupon=coupon, user=user).exists():
        raise CouponError("You have already used this coupon.")
    if coupon.first_paid_order_only and Payment.objects.filter(order__user=user, status=Payment.Status.PAID).exists():
        raise CouponError("This coupon is only available on your first successfully paid order.")
    return coupon, discount_for(coupon, subtotal)


def finalise_redemption(order):
    """Record one successful redemption during verified Razorpay capture."""
    if not order.coupon_id:
        return True
    user_model = order.user.__class__
    user_model.objects.select_for_update().get(pk=order.user_id)
    existing = CouponRedemption.objects.filter(order=order).first()
    if existing:
        return existing.coupon_id == order.coupon_id and existing.user_id == order.user_id
    if CouponRedemption.objects.filter(coupon_id=order.coupon_id, user_id=order.user_id).exists():
        return False
    if order.coupon.first_paid_order_only and Payment.objects.filter(order__user_id=order.user_id, status=Payment.Status.PAID).exclude(order=order).exists():
        return False
    CouponRedemption.objects.create(coupon=order.coupon, user_id=order.user_id, order=order)
    return True
