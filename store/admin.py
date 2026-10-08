from django.contrib import admin
from .models import Category, Product, ProductImage

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "weight", "is_featured", "is_active", "updated_at")
    list_filter = ("category", "is_active", "is_featured")
    list_editable = ("is_featured", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    inlines = [ProductImageInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
