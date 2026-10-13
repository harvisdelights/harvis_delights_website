from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from rest_framework import viewsets
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer
from .forms import CustomerLoginForm, CustomerSignupForm

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
    return render(request, "store/account.html")

def password_recovery(request):
    return render(request, "store/password_recovery.html")

class CustomerPasswordChangeView(PasswordChangeView):
    template_name = "store/password_change.html"
    success_url = reverse_lazy("account")

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related("category").prefetch_related("gallery")
    serializer_class = ProductSerializer
    lookup_field = "slug"
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
