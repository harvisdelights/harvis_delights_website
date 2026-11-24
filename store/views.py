from django.contrib.auth import login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordResetView, PasswordResetConfirmView, PasswordResetCompleteView, PasswordResetDoneView
from django.conf import settings
from urllib.parse import urlsplit
import json
import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Prefetch
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import requests
from rest_framework import viewsets
from .models import Category, CustomerAddress, Order, OrderItem, Payment, Product, ProductReview, ProductVariant
from .serializers import CategorySerializer, ProductSerializer
from .forms import CheckoutAddressForm, CustomerLoginForm, CustomerSignupForm, CustomerPasswordResetForm, ProductReviewForm
from .services.shipping import SELLER_AREA, SELLER_NAME, SELLER_PINCODE, delivery_estimate
from .services.notifications import queue_new_order_emails
from .services.zeptomail import email_configured
from .services import payments
from .services import coupons
from .services import carts

logger = logging.getLogger(__name__)

def health(request):
    return HttpResponse("ok")


def product_media(request, path):
    """Serve product images from the Render persistent disk.

    The application intentionally runs this route itself because product media
    is stored on the service's mounted disk rather than in a separate object
    storage service.  Resolve and validate the path so a media URL cannot read
    a file outside MEDIA_ROOT.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested_file = (media_root / path).resolve()
    allowed_extensions = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}

    if media_root not in requested_file.parents or requested_file.suffix.lower() not in allowed_extensions:
        raise Http404("Media file not found")
    if not requested_file.is_file():
        raise Http404("Media file not found")

    response = FileResponse(requested_file.open("rb"))
    response["Cache-Control"] = "public, max-age=86400"
    return response

def _prepare_products(products):
    """Attach only active variants and a deterministic default for templates."""
    products = list(products)
    for product in products:
        product.active_variants = [variant for variant in product.variants.all() if variant.is_active]
        product.default_variant = next((variant for variant in product.active_variants if variant.is_default), None)
        if not product.default_variant and product.active_variants:
            product.default_variant = product.active_variants[0]
        product.display_price = product.default_variant.price if product.default_variant else product.price
    return products


def home(request):
    featured = _prepare_products(
        Product.objects.filter(is_active=True, is_featured=True).prefetch_related(
            Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True))
        )[:6]
    )
    return render(request, "store/home.html", {"featured": featured})
def products(request):
    products = _prepare_products(
        Product.objects.filter(is_active=True).prefetch_related(
            Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True))
        )
    )
    return render(request, "store/products.html", {"products": products, "categories": Category.objects.all()})
def _product_detail_context(product):
    reviews = product.reviews.filter(is_visible=True).select_related("user")
    summary = reviews.aggregate(average=Avg("rating"))
    return {
        "product": product,
        "product_reviews": reviews,
        "review_count": reviews.count(),
        "average_rating": summary["average"],
    }


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related(
            "gallery", Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True))
        ),
        slug=slug,
        is_active=True,
    )
    _prepare_products([product])
    return render(request, "store/detail.html", _product_detail_context(product))


@login_required
@require_POST
def order_item_review_create(request, number, item_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product", "items__review"),
        number=number,
        user=request.user,
    )
    order_item = get_object_or_404(OrderItem.objects.select_related("product"), pk=item_id, order=order)
    if order.status != Order.Status.DELIVERED:
        messages.error(request, "Reviews become available after this order is marked delivered.")
        return redirect("order_confirmation", number=order.number)
    if ProductReview.objects.filter(order_item=order_item).exists():
        messages.error(request, "You have already reviewed this item from this order.")
        return redirect("order_confirmation", number=order.number)

    form = ProductReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = order_item.product
        review.order_item = order_item
        review.user = request.user
        try:
            review.full_clean()
            review.save()
        except (ValidationError, IntegrityError):
            form.add_error(None, "Your review could not be saved. Please refresh the page and try again.")
        else:
            messages.success(request, "Thank you. Your review has been published.")
            return redirect("order_confirmation", number=order.number)

    return _render_order_confirmation(request, order, review_item_id=order_item.id, review_form=form, status=400)

def signup(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = CustomerSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("account")
    return render(request, "store/auth_form.html", {"form": form, "heading": "Create your account", "intro": "Save your details for a smoother shopping experience.", "submit_label": "Create account", "alternate_url": reverse("login"), "alternate_text": "Already have an account? Sign in"})

def customer_login(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = CustomerLoginForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(request.POST.get("next") or "account")
    return render(request, "store/auth_form.html", {"form": form, "heading": "Welcome back", "intro": "Sign in to your Harvi's Delights account.", "submit_label": "Sign in", "alternate_url": reverse("signup"), "alternate_text": "New here? Create an account", "next": request.GET.get("next", "")})

def customer_logout(request):
    if request.method == "POST":
        logout(request)
    return redirect("home")

@login_required
def account(request):
    return render(request, "store/account.html", {"orders": request.user.orders.prefetch_related("items")[:5]})

class CustomerPasswordResetView(PasswordResetView):
    template_name = "store/password_reset_form.html"
    email_template_name = "store/password_reset_email.txt"
    subject_template_name = "store/password_reset_subject.txt"
    form_class = CustomerPasswordResetForm
    success_url = reverse_lazy("password_reset_done")

    def dispatch(self, request, *args, **kwargs):
        site = urlsplit(settings.PUBLIC_SITE_URL)
        valid_site = bool(site.netloc and not site.username and not site.password and not site.path and not site.query and not site.fragment and (site.scheme == "https" or (settings.DEBUG and site.scheme == "http")))
        if not email_configured() or not valid_site:
            return render(request, "store/password_recovery.html")
        return super().dispatch(request, *args, **kwargs)


class CustomerPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "store/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")


class CustomerPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "store/password_reset_complete.html"


class CustomerPasswordResetDoneView(PasswordResetDoneView):
    template_name = "store/password_reset_done.html"

class CustomerPasswordChangeView(PasswordChangeView):
    template_name = "store/password_change.html"
    success_url = reverse_lazy("account")

def _cart_quantities(raw_cart, *, allow_empty=False):
    try:
        submitted = json.loads(raw_cart)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Your cart could not be read. Please review it.")
    if not isinstance(submitted, list) or (not submitted and not allow_empty) or len(submitted) > 100:
        raise ValueError("Your cart is empty or invalid. Please review it.")
    quantities = {}
    for item in submitted:
        try:
            if not isinstance(item, dict):
                raise ValueError
            raw_id = str(item["id"])
            match = re.fullmatch(r"(\d+)(?::v(\d+))?", raw_id)
            if not match:
                raise ValueError
            product_id = int(match.group(1))
            variant_id = int(match.group(2)) if match.group(2) else None
            quantity = int(str(item["quantity"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("Your cart contains an invalid item. Please review it.")
        key = (product_id, variant_id)
        if (not 1 <= product_id <= 9223372036854775807 or (variant_id is not None and not 1 <= variant_id <= 9223372036854775807)
                or not 1 <= quantity <= 20 or key in quantities):
            raise ValueError("Your cart contains an invalid quantity or duplicate item. Please review it.")
        quantities[key] = quantity
    return quantities


@login_required
@require_POST
def cart_merge(request):
    """Merge an unsigned guest-device cart into the signed-in account cart."""
    try:
        quantities = _cart_quantities(request.POST.get("cart_payload", "[]"), allow_empty=True)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse(carts.merge_guest_cart(request.user, quantities))


@login_required
@require_POST
def cart_mutate(request):
    try:
        product_id = int(request.POST.get("product_id", ""))
        variant_id = int(request.POST.get("variant_id", "")) if request.POST.get("variant_id") else None
        quantity = int(request.POST.get("quantity", "0"))
        expected_version = int(request.POST.get("version", ""))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Invalid cart update."}, status=400)
    if product_id < 1 or (variant_id is not None and variant_id < 1) or expected_version < 0:
        return JsonResponse({"detail": "Invalid cart update."}, status=400)
    try:
        payload, current = carts.mutate(
            request.user,
            action=request.POST.get("action", ""),
            product_id=product_id,
            variant_id=variant_id,
            quantity=quantity,
            expected_version=expected_version,
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    if current is not None:
        return JsonResponse({"detail": "Your cart changed on another device. It has been refreshed; please repeat your last change.", **current}, status=409)
    return JsonResponse(payload)


@dataclass(frozen=True)
class CartLine:
    key: tuple
    product: Product
    variant: ProductVariant | None

    @property
    def price(self):
        return self.variant.price if self.variant else self.product.price

    @property
    def name(self):
        return self.product.name + (f" — {self.variant.name}" if self.variant else "")

    @property
    def shipping_weight_kg(self):
        return self.variant.shipping_weight_kg if self.variant and self.variant.shipping_weight_kg else self.product.shipping_weight_kg


def _cart_products(quantities, lock=False):
    product_ids = {product_id for product_id, _ in quantities}
    variant_ids = {variant_id for _, variant_id in quantities if variant_id}
    product_query = Product.objects.filter(id__in=product_ids, is_active=True).order_by("id")
    variant_query = ProductVariant.objects.filter(id__in=variant_ids, is_active=True)
    if lock:
        product_query = product_query.select_for_update()
        variant_query = variant_query.select_for_update()
    products = {product.id: product for product in product_query}
    variants = {variant.id: variant for variant in variant_query}
    lines, missing = [], []
    for key in quantities:
        product_id, variant_id = key
        product = products.get(product_id)
        variant = variants.get(variant_id) if variant_id else None
        if not product or (variant_id and (not variant or variant.product_id != product_id)):
            missing.append(carts.line_key(product_id, variant_id))
        else:
            lines.append(CartLine(key, product, variant))
    return lines, missing


def _quote_lines(products, quantities):
    return [{"id": carts.line_key(*line.key), "product_id": line.product.id, "variant_id": line.variant.id if line.variant else None, "quantity": quantities[line.key], "price": str(line.price)} for line in products]


def _coupon_snapshot(coupon, discount):
    return {
        "id": coupon.pk if coupon else None,
        "code": coupon.code if coupon else "",
        "discount_total": str(discount),
    }


def _checkout_pricing(products, quantities, user, coupon_code):
    subtotal = sum((line.price * quantities[line.key] for line in products), Decimal("0"))
    coupon, discount = coupons.validate_coupon_for_checkout(code=coupon_code, user=user, subtotal=subtotal)
    return subtotal, coupon, discount, subtotal - discount


@login_required
def cart_review(request):
    if request.method != "POST":
        return JsonResponse({"detail": "POST required."}, status=405)
    try:
        quantities = _cart_quantities(request.POST.get("cart_payload", ""))
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    products, missing = _cart_products(quantities)
    if missing:
        return JsonResponse({"detail": "Some products are no longer available. Remove them from your cart before placing your order.", "unavailable_ids": missing}, status=409)
    try:
        subtotal, coupon, discount, total = _checkout_pricing(products, quantities, request.user, request.POST.get("coupon_code", ""))
    except coupons.CouponError as exc:
        return JsonResponse({"detail": str(exc), "coupon_error": True}, status=400)
    lines = _quote_lines(products, quantities)
    items = [{"id": carts.line_key(*line.key), "name": line.name, "quantity": quantities[line.key], "price": str(line.price), "line_total": str(line.price * quantities[line.key])} for line in products]
    if subtotal > Decimal("99999999.99"):
        return JsonResponse({"detail": "Your order total exceeds the supported limit. Please reduce your cart."}, status=400)
    coupon_data = _coupon_snapshot(coupon, discount)
    quote = signing.dumps({"user": request.user.pk, "lines": lines, "coupon": coupon_data}, salt="store.checkout.quote", compress=True)
    return JsonResponse({"items": items, "subtotal": str(subtotal), "discount": str(discount), "coupon": coupon_data["code"], "total": str(total), "quote": quote, "checkout_id": str(uuid.uuid4())})

@login_required
def shipping_estimate(request):
    if request.method != "POST":
        return JsonResponse({"detail": "POST required."}, status=405)
    try:
        quantities = _cart_quantities(request.POST.get("cart_payload", ""))
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    products, missing = _cart_products(quantities)
    pincode = request.POST.get("pincode", "").strip()
    if missing or len(pincode) != 6 or not pincode.isdigit():
        return JsonResponse({"detail": "Add products and enter a valid pincode."}, status=400)
    subtotal = sum((line.price * quantities[line.key] for line in products), Decimal("0"))
    weight = sum((line.shipping_weight_kg * quantities[line.key] for line in products), Decimal("0"))
    estimate = delivery_estimate(pincode, weight, subtotal)
    estimate["origin"] = f"{SELLER_NAME}, {SELLER_AREA} – {SELLER_PINCODE}"
    return JsonResponse(estimate)

@login_required
def checkout(request):
    form = CheckoutAddressForm(request.POST if request.method == "POST" else None, initial={"full_name": request.user.get_full_name(), "phone": ""})
    checkout_id = uuid.uuid4()
    if request.method == "POST" and not payments.configured():
        # Fail closed: an online-only store must never create an order that a
        # customer cannot immediately take to the configured payment gateway.
        form.add_error(None, "Online payment is temporarily unavailable. No order was created.")
        return render(request, "store/checkout.html", {"form": form, "checkout_id": checkout_id, "seller_origin": f"{SELLER_NAME}, {SELLER_AREA} – {SELLER_PINCODE}", "payment_enabled": False, "payment_mode": settings.RAZORPAY_MODE})
    if request.method == "POST":
        try:
            checkout_id = uuid.UUID(request.POST.get("checkout_id", ""))
        except (ValueError, TypeError, AttributeError):
            form.add_error(None, "This checkout has expired. Please reload the page and try again.")
        else:
            existing = Order.objects.filter(checkout_id=checkout_id, user=request.user).first()
            if existing:
                return redirect("order_confirmation", number=existing.number)
            try:
                quantities = _cart_quantities(request.POST.get("cart_payload", ""))
                quote = signing.loads(request.POST.get("cart_quote", ""), salt="store.checkout.quote", max_age=1800)
                if quote.get("user") != request.user.pk:
                    raise ValueError("Please review your cart before placing the order.")
            except (ValueError, signing.BadSignature, AttributeError):
                form.add_error(None, "Your cart review is missing or expired. Please review the current prices and try again.")
            else:
                if form.is_valid():
                    products, missing = _cart_products(quantities)
                    try:
                        subtotal, coupon, discount, total = _checkout_pricing(products, quantities, request.user, quote.get("coupon", {}).get("code", ""))
                    except (coupons.CouponError, AttributeError) as exc:
                        form.add_error(None, str(exc))
                        subtotal = coupon = discount = total = None
                    if subtotal is None:
                        pass
                    elif (missing or quote.get("lines") != _quote_lines(products, quantities)
                            or quote.get("coupon") != _coupon_snapshot(coupon, discount)):
                        form.add_error(None, "Your cart or prices changed. Please review the current items and total before ordering.")
                    else:
                        weight = sum((line.shipping_weight_kg * quantities[line.key] for line in products), Decimal("0"))
                        estimate = delivery_estimate(form.cleaned_data["pincode"], weight, subtotal)
                        try:
                            with transaction.atomic():
                                products, missing = _cart_products(quantities, lock=True)
                                subtotal, coupon, discount, total = _checkout_pricing(products, quantities, request.user, quote.get("coupon", {}).get("code", ""))
                                if (missing or quote.get("lines") != _quote_lines(products, quantities)
                                        or quote.get("coupon") != _coupon_snapshot(coupon, discount)):
                                    raise ValueError("Your cart or prices changed. Please review the current items and total before ordering.")
                                address = CustomerAddress.objects.create(user=request.user, **{key: form.cleaned_data[key] for key in ("full_name", "phone", "line1", "line2", "city", "state", "pincode")})
                                order = Order.objects.create(checkout_id=checkout_id, user=request.user, address=address, environment=settings.RAZORPAY_MODE if settings.RAZORPAY_MODE in ("test", "live") else Order.Environment.LEGACY, status=Order.Status.PENDING, subtotal=subtotal, coupon=coupon, coupon_code=coupon.code if coupon else "", discount_total=discount, total=total, delivery_estimate=estimate["message"], shiprocket_courier=estimate["courier"])
                                OrderItem.objects.bulk_create([
                                    OrderItem(
                                        order=order,
                                        product=line.product,
                                        variant=line.variant,
                                        product_name=line.product.name,
                                        variant_name=line.variant.name if line.variant else "",
                                        unit_price=line.price,
                                        quantity=quantities[line.key],
                                    )
                                    for line in products
                                ])
                                transaction.on_commit(lambda user=request.user, ordered=quantities.copy(): carts.remove_checked_out_quantities(user, ordered), robust=True)
                                queue_new_order_emails(order)
                        except ValueError as exc:
                            form.add_error(None, str(exc))
                        except IntegrityError:
                            existing = Order.objects.filter(checkout_id=checkout_id, user=request.user).first()
                            if existing:
                                return redirect("order_confirmation", number=existing.number)
                            if Order.objects.filter(checkout_id=checkout_id).exists():
                                form.add_error(None, "This checkout reference has already been used. Please reload the page.")
                            else:
                                raise
                        else:
                            return redirect("order_confirmation", number=order.number)
    return render(request, "store/checkout.html", {"form": form, "checkout_id": checkout_id, "seller_origin": f"{SELLER_NAME}, {SELLER_AREA} – {SELLER_PINCODE}", "payment_enabled": payments.configured(), "payment_mode": settings.RAZORPAY_MODE})

@login_required
def order_confirmation(request, number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product", "items__review"),
        number=number,
        user=request.user,
    )
    try:
        review_item_id = int(request.GET.get("review", ""))
    except (TypeError, ValueError):
        review_item_id = None
    return _render_order_confirmation(request, order, review_item_id=review_item_id)


def _render_order_confirmation(request, order, review_item_id=None, review_form=None, status=200):
    eligible_mode = order.environment == settings.RAZORPAY_MODE or (settings.RAZORPAY_MODE == "test" and order.environment == Order.Environment.LEGACY)
    for item in order.items.all():
        item.can_review = order.status == Order.Status.DELIVERED and not hasattr(item, "review")
        item.show_review_form = item.can_review and item.id == review_item_id
        item.review_form = review_form if item.show_review_form else ProductReviewForm()
    return render(
        request,
        "store/order_confirmation.html",
        {
            "order": order,
            "payment_enabled": payments.configured() and eligible_mode,
            "payment_mode": settings.RAZORPAY_MODE,
        },
        status=status,
    )


@login_required
@require_POST
def payment_start(request, number):
    order = get_object_or_404(Order, number=number, user=request.user)
    if not payments.configured():
        return JsonResponse({"detail": "Payments are not configured."}, status=503)
    if order.environment != settings.RAZORPAY_MODE and not (settings.RAZORPAY_MODE == "test" and order.environment == Order.Environment.LEGACY):
        return JsonResponse({"detail": "This older order cannot be paid in live mode. Please place a new order."}, status=409)
    if order.status != Order.Status.PENDING or order.total < Decimal("1.00") or order.shipping_charge != 0:
        return JsonResponse({"detail": "This order is not eligible for payment."}, status=400)
    try:
        payment, created = Payment.objects.get_or_create(order=order, defaults={"environment": settings.RAZORPAY_MODE})
    except IntegrityError:
        payment = Payment.objects.get(order=order)
        created = False
    if not payments.compatible(payment):
        return JsonResponse({"detail": "This payment belongs to another environment. Please place a new order."}, status=409)
    if created:
        try:
            remote = payments.request_api("POST", "orders", json={"amount": int(order.total * 100), "currency": "INR", "receipt": order.number})
            if (not isinstance(remote.get("id"), str) or not remote["id"].startswith("order_")
                    or len(remote["id"]) > 100 or remote.get("amount") != int(order.total * 100)
                    or remote.get("currency") != "INR"):
                raise ValueError("Unexpected gateway order response")
            payment.gateway_order_id = remote["id"]
            payment.status = Payment.Status.PENDING
            payment.save(update_fields=["gateway_order_id", "status", "updated_at"])
        except (requests.RequestException, ValueError, TypeError):
            # The remote order may exist despite a timeout. Never create another automatically.
            payment.status = Payment.Status.REVIEW
            payment.save(update_fields=["status", "updated_at"])
            logger.warning("Razorpay order creation requires review for %s", order.number)
    if payment.status == Payment.Status.PAID:
        return JsonResponse({"detail": "Payment already captured.", "paid": True})
    if payment.status != Payment.Status.PENDING:
        return JsonResponse({"detail": "Payment setup is being reviewed. Please contact the seller before retrying."}, status=503)
    return JsonResponse({"key": settings.RAZORPAY_KEY_ID, "order_id": payment.gateway_order_id,
                         "amount": int(order.total * 100), "currency": "INR", "name": "Harvi's Delights", "reference": order.number})


@login_required
@require_POST
def payment_verify(request, number):
    payment = get_object_or_404(Payment.objects.select_related("order"), order__number=number, order__user=request.user)
    if not payments.configured() or not payment.gateway_order_id or not payments.compatible(payment):
        return JsonResponse({"detail": "Payment is not configured."}, status=503)
    gateway_order = request.POST.get("razorpay_order_id", "")
    payment_id = request.POST.get("razorpay_payment_id", "")
    signature = request.POST.get("razorpay_signature", "")
    if (gateway_order != payment.gateway_order_id or not re.fullmatch(r"pay_[A-Za-z0-9]{1,96}", payment_id)
            or not payments.signature_valid(f"{payment.gateway_order_id}|{payment_id}".encode(), signature, settings.RAZORPAY_KEY_SECRET)):
        return JsonResponse({"detail": "Payment verification failed."}, status=400)
    try:
        entity = payments.request_api("GET", f"payments/{payment_id}")
        if entity.get("id") == payment_id and payments.record_capture(payment.gateway_order_id, entity):
            return JsonResponse({"paid": True})
    except (requests.RequestException, ValueError, TypeError, IntegrityError):
        logger.warning("Payment verification pending for %s", number)
    return JsonResponse({"paid": False, "detail": "Payment is awaiting confirmation. Check this order again shortly."}, status=202)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if not payments.configured() or not payments.signature_valid(request.body, request.headers.get("X-Razorpay-Signature"), settings.RAZORPAY_WEBHOOK_SECRET):
        return HttpResponse(status=400)
    try:
        payload = json.loads(request.body)
        if payload.get("event") == "payment.captured":
            entity = payload["payload"]["payment"]["entity"]
            if not payments.record_capture(entity.get("order_id"), entity):
                return HttpResponse(status=400)
        elif payload.get("event") in ("refund.created", "refund.processed", "refund.failed"):
            refund = payload["payload"]["refund"]["entity"]
            payment_id = refund["payment_id"]
            if not isinstance(payment_id, str) or not re.fullmatch(r"pay_[A-Za-z0-9]{1,96}", payment_id):
                return HttpResponse(status=400)
            entity = payments.request_api("GET", f"payments/{payment_id}")
            if entity.get("id") != payment_id or not payments.flag_refund(entity):
                return HttpResponse(status=503)
    except requests.RequestException:
        return HttpResponse(status=503)
    except (ValueError, TypeError, KeyError, AttributeError, IntegrityError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related("category").prefetch_related("gallery", Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True)))
    serializer_class = ProductSerializer
    lookup_field = "slug"
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
