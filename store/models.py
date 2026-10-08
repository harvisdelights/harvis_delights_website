from django.db import models
from django.urls import reverse

class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    def __str__(self): return self.name

class Product(models.Model):
    category = models.ForeignKey(Category, related_name="products", on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True)
    short_description = models.CharField(max_length=220)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    weight = models.CharField(max_length=40, blank=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    flipkart_url = models.URLField(blank=True, help_text="Optional product listing URL on Flipkart")
    meesho_url = models.URLField(blank=True, help_text="Optional product listing URL on Meesho")
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["-is_featured", "name"]
    def __str__(self): return self.name
    def get_absolute_url(self): return reverse("product_detail", args=[self.slug])

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="gallery", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=140, blank=True)
    position = models.PositiveIntegerField(default=0)
    class Meta: ordering = ["position", "id"]
