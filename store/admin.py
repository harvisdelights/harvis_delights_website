from django.contrib import admin
from django.contrib import messages
from django import forms
from django.db import IntegrityError, transaction
from django.utils.html import format_html_join
import requests
from .services import payments
from .models import Cart, CartItem, Category, Coupon, CouponRedemption, CustomerAddress, Order, OrderEmail, OrderItem, Payment, Product, ProductImage, ProductReview, ProductVariant
from .services.notifications import deliver_order_email, queue_order_status_email

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "static_image_path", "alt_text", "position")


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("name", "price", "shipping_weight_kg", "sku", "position", "is_default", "is_active")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "weight", "is_featured", "is_active", "updated_at")
    list_filter = ("category", "is_active", "is_featured")
    list_editable = ("is_featured", "is_active")
    fieldsets = (
        ("Product details", {"fields": ("category", "name", "slug", "short_description", "description", "price", "weight", "shipping_weight_kg")}),
        ("Photos", {"fields": ("image", "static_image_path")}),
        ("Marketplace links", {"fields": ("flipkart_url", "meesho_url")}),
        ("Visibility", {"fields": ("is_featured", "is_active")}),
    )
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    inlines = [ProductVariantInline, ProductImageInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("product", "variant", "quantity", "created_at", "updated_at")
    can_delete = False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "version", "updated_at")
    search_fields = ("user__email", "user__username")
    readonly_fields = ("user", "version", "created_at", "updated_at")
    inlines = [CartItemInline]

    def has_add_permission(self, request):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "maximum_discount", "minimum_order_value", "first_paid_order_only", "show_on_storefront", "is_active", "starts_at", "expires_at")
    list_filter = ("is_active", "show_on_storefront", "first_paid_order_only", "discount_type")
    search_fields = ("code",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "created_at")
    search_fields = ("coupon__code", "user__email", "order__number")
    readonly_fields = ("coupon", "user", "order", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "rating", "title", "user", "order_item", "is_visible", "created_at")
    list_filter = ("rating", "is_visible", "created_at")
    list_editable = ("is_visible",)
    search_fields = ("product__name", "user__email", "title", "body", "order_item__order__number")
    readonly_fields = ("product", "order_item", "user", "rating", "title", "body", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "variant", "product_name", "variant_name", "unit_price", "quantity")
    can_delete = False


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def clean_status(self):
        status = self.cleaned_data["status"]
        if (self.instance.pk and self.instance.environment == Order.Environment.LIVE
                and status in (Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.DELIVERED)):
            payment = Payment.objects.select_for_update().filter(order=self.instance).first()
            if not payment or payment.environment != Payment.Environment.LIVE or payment.status != Payment.Status.PAID:
                raise forms.ValidationError("Live orders can only be fulfilled when their live payment is captured and not under review.")
        return status

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = ("number", "user", "environment", "status", "payment_status", "total", "delivery_estimate", "created_at")
    list_filter = ("environment", "status")
    search_fields = ("number", "user__email", "user__first_name")
    readonly_fields = ("number", "checkout_id", "user", "environment", "address", "shipping_address", "subtotal", "coupon", "coupon_code", "discount_total", "shipping_charge", "total", "delivery_estimate", "shiprocket_courier", "created_at", "updated_at")
    inlines = [OrderItemInline]

    @admin.display(description="Online payment")
    def payment_status(self, obj):
        try:
            return obj.payment.get_status_display()
        except Payment.DoesNotExist:
            return "Not paid online"

    @admin.display(description="Delivery address")
    def shipping_address(self, obj):
        """Show the delivery-address record created with this checkout."""
        if not obj.address_id:
            return "No delivery address recorded"
        address = obj.address
        lines = [address.full_name, address.line1]
        if address.line2:
            lines.append(address.line2)
        lines.extend((f"{address.city}, {address.state} - {address.pincode}", f"Phone: {address.phone}"))
        return format_html_join("<br>", "{}", ((line,) for line in lines))

    def save_model(self, request, obj, form, change):
        status_changed = change and "status" in form.changed_data
        super().save_model(request, obj, form, change)
        if status_changed:
            queue_order_status_email(obj)


@admin.register(OrderEmail)
class OrderEmailAdmin(admin.ModelAdmin):
    list_display = ("order", "recipient", "subject", "status", "attempts", "created_at", "sent_at")
    list_filter = ("status",)
    search_fields = ("order__number", "recipient")
    readonly_fields = ("order", "recipient", "subject", "body", "status", "attempts", "last_error", "created_at", "sent_at")
    actions = ["retry_emails"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Retry selected pending or failed emails")
    def retry_emails(self, request, queryset):
        ids = list(queryset.filter(status__in=[OrderEmail.Status.PENDING, OrderEmail.Status.FAILED]).values_list("id", flat=True))
        for notification_id in ids:
            transaction.on_commit(lambda pk=notification_id: deliver_order_email(pk), robust=True)
        self.message_user(request, f"Scheduled {len(ids)} email(s) for retry. Check their status after the page reloads.")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "environment", "status", "gateway_order_id", "gateway_payment_id", "updated_at")
    list_filter = ("environment", "status")
    readonly_fields = ("order", "environment", "status", "gateway_order_id", "gateway_payment_id", "created_at", "updated_at")
    search_fields = ("order__number", "gateway_order_id", "gateway_payment_id")
    actions = ["reconcile_pending_payments"]

    @admin.action(description="Check selected awaiting or captured payments with Razorpay")
    def reconcile_pending_payments(self, request, queryset):
        recovered = 0
        not_recovered = 0
        for payment in queryset.select_related("order"):
            try:
                if payments.reconcile_pending(payment):
                    recovered += 1
                else:
                    not_recovered += 1
            except (requests.RequestException, ValueError, TypeError, IntegrityError, transaction.TransactionManagementError):
                not_recovered += 1
        self.message_user(request, f"Confirmed {recovered} captured payment(s); {not_recovered} need review or are not eligible. Check Razorpay before retrying.", level=messages.WARNING if not_recovered else messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "city", "state", "pincode", "phone")
    search_fields = ("full_name", "user__email", "pincode", "phone")
