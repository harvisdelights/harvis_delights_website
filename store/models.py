import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.templatetags.static import static
from django.urls import reverse


def validate_static_product_image_path(value):
    """Allow only repository assets under store/static/store/product-images/."""
    if not value:
        return
    path = PurePosixPath(value)
    allowed_extensions = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
    if (
        "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or not value.startswith("product-images/")
        or path.suffix.lower() not in allowed_extensions
    ):
        raise ValidationError(
            "Use a relative image path under product-images/, for example "
            "product-images/raisins/afghani-black-raisins-main.webp."
        )

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
    static_image_path = models.CharField(
        max_length=255,
        blank=True,
        validators=[validate_static_product_image_path],
        help_text="Optional Git-managed image path, e.g. product-images/almonds/california-almonds-main.webp. Takes priority over the uploaded image.",
    )
    shipping_weight_kg = models.DecimalField(max_digits=5, decimal_places=3, default=0.500, help_text="Used for delivery estimates.")
    flipkart_url = models.URLField(blank=True, help_text="Optional product listing URL on Flipkart")
    meesho_url = models.URLField(blank=True, help_text="Optional product listing URL on Meesho")
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ["-is_featured", "name"]
    def __str__(self): return self.name
    def get_absolute_url(self): return reverse("product_detail", args=[self.slug])

    @property
    def display_image_url(self):
        if self.static_image_path:
            return static(f"store/{self.static_image_path}")
        return self.image.url if self.image else ""

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="gallery", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/gallery/", blank=True, null=True)
    static_image_path = models.CharField(
        max_length=255,
        blank=True,
        validators=[validate_static_product_image_path],
        help_text="Optional Git-managed image path under product-images/. Takes priority over the uploaded image.",
    )
    alt_text = models.CharField(max_length=140, blank=True)
    position = models.PositiveIntegerField(default=0)
    class Meta: ordering = ["position", "id"]

    @property
    def display_image_url(self):
        if self.static_image_path:
            return static(f"store/{self.static_image_path}")
        return self.image.url if self.image else ""


class CustomerAddress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="addresses", on_delete=models.CASCADE)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    line1 = models.CharField(max_length=180, verbose_name="Address line 1")
    line2 = models.CharField(max_length=180, blank=True, verbose_name="Address line 2")
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.full_name} — {self.pincode}"


class Order(models.Model):
    class Environment(models.TextChoices):
        LEGACY = "legacy", "Legacy / unverified"
        TEST = "test", "Test"
        LIVE = "live", "Live"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=28, unique=True, editable=False)
    environment = models.CharField(max_length=12, choices=Environment.choices, default=Environment.LEGACY, editable=False)
    checkout_id = models.UUIDField(null=True, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.PROTECT)
    address = models.ForeignKey(CustomerAddress, related_name="orders", null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_estimate = models.CharField(max_length=160, blank=True)
    shiprocket_courier = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f"HD-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="order_items", on_delete=models.PROTECT)
    product_name = models.CharField(max_length=160)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class Payment(models.Model):
    class Environment(models.TextChoices):
        LEGACY = "legacy", "Legacy / unverified"
        TEST = "test", "Test"
        LIVE = "live", "Live"

    class Status(models.TextChoices):
        CREATING = "creating", "Creating gateway order"
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Payment captured"
        REVIEW = "review", "Needs manual review"

    order = models.OneToOneField(Order, related_name="payment", on_delete=models.PROTECT)
    environment = models.CharField(max_length=12, choices=Environment.choices, default=Environment.LEGACY, editable=False)
    gateway_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    gateway_payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class OrderEmail(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Accepted by provider"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(Order, related_name="email_notifications", on_delete=models.CASCADE)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    # Null is retained for historical/general notifications. Payment receipts
    # use a unique key so repeated Razorpay callbacks cannot send duplicates.
    deduplication_key = models.CharField(max_length=180, unique=True, null=True, blank=True, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.number}: {self.subject}"
