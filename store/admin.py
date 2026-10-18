from django.contrib import admin
from django.contrib import messages
from django.db import IntegrityError, transaction
import requests
from .services import payments
from .models import Category, CustomerAddress, Order, OrderEmail, OrderItem, Payment, Product, ProductImage
from .services.notifications import deliver_order_email, queue_order_status_email

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
    list_display = ("number", "user", "environment", "status", "payment_status", "total", "delivery_estimate", "created_at")
    list_filter = ("environment", "status", "payment_method")
    search_fields = ("number", "user__email", "user__first_name")
    readonly_fields = ("number", "checkout_id", "user", "environment", "address", "subtotal", "shipping_charge", "total", "delivery_estimate", "shiprocket_courier", "created_at", "updated_at")
    inlines = [OrderItemInline]

    @admin.display(description="Online payment")
    def payment_status(self, obj):
        try:
            return obj.payment.get_status_display()
        except Payment.DoesNotExist:
            return "Not paid online"

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

    @admin.action(description="Check selected awaiting payments with Razorpay")
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
