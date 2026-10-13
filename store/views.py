from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
import json
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from rest_framework import viewsets
from .models import Category, CustomerAddress, Order, OrderItem, Product
from .serializers import CategorySerializer, ProductSerializer
from .forms import CheckoutAddressForm, CustomerLoginForm, CustomerSignupForm
from .services.shipping import SELLER_AREA, SELLER_NAME, SELLER_PINCODE, delivery_estimate

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

def password_recovery(request):
    return render(request, "store/password_recovery.html")

class CustomerPasswordChangeView(PasswordChangeView):
    template_name = "store/password_change.html"
    success_url = reverse_lazy("account")

def _validated_cart(raw_cart):
    try:
        submitted = json.loads(raw_cart)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(submitted, list) or not submitted:
        return []
    quantities = {}
    for item in submitted:
        try:
            product_id, quantity = int(item["id"]), int(item["quantity"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < quantity <= 20:
            quantities[product_id] = min(20, quantities.get(product_id, 0) + quantity)
    products = Product.objects.filter(id__in=quantities, is_active=True)
    return [(product, quantities[product.id]) for product in products]

@login_required
def shipping_estimate(request):
    if request.method != "POST":
        return JsonResponse({"detail": "POST required."}, status=405)
    cart = _validated_cart(request.POST.get("cart_payload", ""))
    pincode = request.POST.get("pincode", "").strip()
    if not cart or len(pincode) != 6 or not pincode.isdigit():
        return JsonResponse({"detail": "Add products and enter a valid pincode."}, status=400)
    subtotal = sum((product.price * quantity for product, quantity in cart), Decimal("0"))
    weight = sum((product.shipping_weight_kg * quantity for product, quantity in cart), Decimal("0"))
    estimate = delivery_estimate(pincode, weight, subtotal)
    estimate["origin"] = f"{SELLER_NAME}, {SELLER_AREA} – {SELLER_PINCODE}"
    return JsonResponse(estimate)

@login_required
def checkout(request):
    cart = _validated_cart(request.POST.get("cart_payload", "") if request.method == "POST" else "")
    form = CheckoutAddressForm(request.POST or None, initial={"full_name": request.user.get_full_name(), "phone": ""})
    if request.method == "POST" and form.is_valid() and cart:
        subtotal = sum((product.price * quantity for product, quantity in cart), Decimal("0"))
        weight = sum((product.shipping_weight_kg * quantity for product, quantity in cart), Decimal("0"))
        estimate = delivery_estimate(form.cleaned_data["pincode"], weight, subtotal)
        with transaction.atomic():
            address = CustomerAddress.objects.create(user=request.user, **{key: form.cleaned_data[key] for key in ("full_name", "phone", "line1", "line2", "city", "state", "pincode")})
            order = Order.objects.create(user=request.user, address=address, subtotal=subtotal, total=subtotal, delivery_estimate=estimate["message"], shiprocket_courier=estimate["courier"])
            OrderItem.objects.bulk_create([OrderItem(order=order, product=product, product_name=product.name, unit_price=product.price, quantity=quantity) for product, quantity in cart])
        return redirect("order_confirmation", number=order.number)
    if request.method == "POST" and not cart:
        form.add_error(None, "Your cart is empty or contains unavailable products.")
    return render(request, "store/checkout.html", {"form": form, "seller_origin": f"{SELLER_NAME}, {SELLER_AREA} – {SELLER_PINCODE}"})

@login_required
def order_confirmation(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number, user=request.user)
    return render(request, "store/order_confirmation.html", {"order": order})

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related("category").prefetch_related("gallery")
    serializer_class = ProductSerializer
    lookup_field = "slug"
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
