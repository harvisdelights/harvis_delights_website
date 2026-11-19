from django.db.models import Q
from django.utils import timezone

from store.models import Coupon, CouponRedemption, Payment


def storefront_coupon(request):
    """Expose one active public offer without advertising it to ineligible buyers."""
    now = timezone.now()
    candidates = Coupon.objects.filter(show_on_storefront=True, is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(expires_at__isnull=True) | Q(expires_at__gt=now),
    ).order_by("-storefront_priority", "code")

    if not request.user.is_authenticated:
        return {"storefront_coupon": candidates.first()}

    for coupon in candidates:
        if CouponRedemption.objects.filter(coupon=coupon, user=request.user).exists():
            continue
        if coupon.first_paid_order_only and Payment.objects.filter(order__user=request.user, status=Payment.Status.PAID).exists():
            continue
        return {"storefront_coupon": coupon}
    return {"storefront_coupon": None}
