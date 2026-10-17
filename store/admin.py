from django.contrib import admin
from .models import Category, CustomerAddress, Order, OrderItem, Product, ProductImage

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "weight", "is_featured", "is_active", "updated_at")
    list_filter = ("category", "is_active", "is_featured")
    list_editable = ("is_featured", "is_active")
    fieldsets = (
        ("Product details", {"fields": ("category", "name", "slug", "short_description", "description", "price", "weight", "shipping_weight_kg")}),
        ("Photos", {"fields": ("image",)}),
        ("Marketplace links", {"fields": ("flipkart_url", "meesho_url")}),
        ("Visibility", {"fields": ("is_featured", "is_active")}),
    )
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    inlines = [ProductImageInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "unit_price", "quantity")
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "status", "total", "delivery_estimate", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("number", "user__email", "user__first_name")
    readonly_fields = ("number", "checkout_id", "user", "address", "subtotal", "shipping_charge", "total", "delivery_estimate", "shiprocket_courier", "created_at", "updated_at")
    inlines = [OrderItemInline]

@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "city", "state", "pincode", "phone")
    search_fields = ("full_name", "user__email", "pincode", "phone")
