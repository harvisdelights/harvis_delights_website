from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView, PasswordResetView, PasswordResetConfirmView, PasswordResetCompleteView, PasswordResetDoneView
from django.conf import settings
from urllib.parse import urlsplit
import json
import logging
import re
import uuid
from decimal import Decimal

from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import requests
from rest_framework import viewsets
from .models import Category, CustomerAddress, Order, OrderItem, Payment, Product
from .serializers import CategorySerializer, ProductSerializer
from .forms import CheckoutAddressForm, CustomerLoginForm, CustomerSignupForm, CustomerPasswordResetForm
from .services.shipping import SELLER_AREA, SELLER_NAME, SELLER_PINCODE, delivery_estimate
from .services.notifications import queue_new_order_emails
from .services.zeptomail import email_configured
from .services import payments

logger = logging.getLogger(__name__)

def health(request):
    return HttpResponse("ok")

def home(request):
    return render(request, "store/home.html", {"featured": Product.objects.filter(is_active=True, is_featured=True)[:6]})
def products(request):
    return render(request, "store/products.html", {"products": Product.objects.filter(is_active=True), "categories": Category.objects.all()})
def product_detail(request, slug):
    return render(request, "store/detail.html", {"product": get_object_or_404(Product, slug=slug, is_active=True)})

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

def _cart_quantities(raw_cart):
    try:
        submitted = json.loads(raw_cart)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Your cart could not be read. Please review it.")
    if not isinstance(submitted, list) or not submitted or len(submitted) > 100:
        raise ValueError("Your cart is empty or invalid. Please review it.")
    quantities = {}
    for item in submitted:
        try:
            if not isinstance(item, dict):
                raise ValueError
            product_id = int(str(item["id"]))
            quantity = int(str(item["quantity"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("Your cart contains an invalid item. Please review it.")
        if not 1 <= product_id <= 9223372036854775807 or not 1 <= quantity <= 20 or product_id in quantities:
            raise ValueError("Your cart contains an invalid quantity or duplicate item. Please review it.")
        quantities[product_id] = quantity
    return quantities


def _cart_products(quantities, lock=False):
    products = Product.objects.filter(id__in=quantities, is_active=True).order_by("id")
    if lock:
        products = products.select_for_update()
    products = list(products)
    missing = sorted(set(quantities) - {product.id for product in products})
    return products, missing


def _quote_lines(products, quantities):
    return [{"id": product.id, "quantity": quantities[product.id], "price": str(product.price)} for product in products]


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
    lines = _quote_lines(products, quantities)
    items = [{"id": product.id, "name": product.name, "quantity": quantities[product.id], "price": str(product.price), "line_total": str(product.price * quantities[product.id])} for product in products]
    total = sum((product.price * quantities[product.id] for product in products), Decimal("0"))
    if total > Decimal("99999999.99"):
        return JsonResponse({"detail": "Your order total exceeds the supported limit. Please reduce your cart."}, status=400)
    quote = signing.dumps({"user": request.user.pk, "lines": lines}, salt="store.checkout.quote", compress=True)
    return JsonResponse({"items": items, "total": str(total), "quote": quote, "checkout_id": str(uuid.uuid4())})

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
    subtotal = sum((product.price * quantities[product.id] for product in products), Decimal("0"))
    weight = sum((product.shipping_weight_kg * quantities[product.id] for product in products), Decimal("0"))
    estimate = delivery_estimate(pincode, weight, subtotal)
    estimate["origin"] = f"{SELLER_NAME}, {SELLER_AREA} – {SELLER_PINCODE}"
    return JsonResponse(estimate)

@login_required
def checkout(request):
    form = CheckoutAddressForm(request.POST if request.method == "POST" else None, initial={"full_name": request.user.get_full_name(), "phone": ""})
    checkout_id = uuid.uuid4()
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
                    if missing or quote.get("lines") != _quote_lines(products, quantities):
                        form.add_error(None, "Your cart or prices changed. Please review the current items and total before ordering.")
                    else:
                        subtotal = sum((p.price * quantities[p.id] for p in products), Decimal("0"))
                        weight = sum((p.shipping_weight_kg * quantities[p.id] for p in products), Decimal("0"))
                        estimate = delivery_estimate(form.cleaned_data["pincode"], weight, subtotal)
                        try:
                            with transaction.atomic():
                                products, missing = _cart_products(quantities, lock=True)
                                if missing or quote.get("lines") != _quote_lines(products, quantities):
                                    raise ValueError("Your cart or prices changed. Please review the current items and total before ordering.")
                                address = CustomerAddress.objects.create(user=request.user, **{key: form.cleaned_data[key] for key in ("full_name", "phone", "line1", "line2", "city", "state", "pincode")})
                                order = Order.objects.create(checkout_id=checkout_id, user=request.user, address=address, environment=Order.Environment.TEST if settings.RAZORPAY_MODE == "test" else Order.Environment.LEGACY, status=Order.Status.CONFIRMED, subtotal=subtotal, total=subtotal, delivery_estimate=estimate["message"], shiprocket_courier=estimate["courier"])
                                OrderItem.objects.bulk_create([OrderItem(order=order, product=p, product_name=p.name, unit_price=p.price, quantity=quantities[p.id]) for p in products])
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
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number, user=request.user)
    eligible_mode = settings.RAZORPAY_MODE == "test" or order.environment == Order.Environment.LIVE
    return render(request, "store/order_confirmation.html", {"order": order, "payment_enabled": payments.configured() and eligible_mode, "payment_mode": settings.RAZORPAY_MODE})


@login_required
@require_POST
def payment_start(request, number):
    order = get_object_or_404(Order, number=number, user=request.user)
    if not payments.configured():
        return JsonResponse({"detail": "Payments are not configured."}, status=503)
    if settings.RAZORPAY_MODE == "live" and order.environment != Order.Environment.LIVE:
        return JsonResponse({"detail": "This older order cannot be paid in live mode. Please place a new order."}, status=409)
    if order.status not in (Order.Status.PENDING, Order.Status.CONFIRMED) or order.total < Decimal("1.00") or order.shipping_charge != 0:
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
    except (ValueError, TypeError, KeyError, AttributeError, IntegrityError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related("category").prefetch_related("gallery")
    serializer_class = ProductSerializer
    lookup_field = "slug"
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
