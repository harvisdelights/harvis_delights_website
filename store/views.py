from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import viewsets
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

def health(request):
    return HttpResponse("ok")

def home(request):
    return render(request, "store/home.html", {"featured": Product.objects.filter(is_active=True, is_featured=True)[:6]})
def products(request):
    return render(request, "store/products.html", {"products": Product.objects.filter(is_active=True), "categories": Category.objects.all()})
def product_detail(request, slug):
    return render(request, "store/detail.html", {"product": get_object_or_404(Product, slug=slug, is_active=True)})

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related("category").prefetch_related("gallery")
    serializer_class = ProductSerializer
    lookup_field = "slug"
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
