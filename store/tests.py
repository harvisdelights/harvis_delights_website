import json
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Cart, CartItem, Category, Coupon, CustomerAddress, Order, OrderEmail, OrderItem, Payment, Product, ProductImage, ProductReview, ProductVariant
from .services import carts


class ProductMediaTests(TestCase):
    def test_product_image_is_served_from_media_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "products" / "almonds.jpg"
            image_path.parent.mkdir()
            image_path.write_bytes(b"image-content")

            with self.settings(MEDIA_ROOT=temporary_directory):
                response = self.client.get("/media/products/almonds.jpg")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"image-content")
            self.assertEqual(response["Cache-Control"], "public, max-age=86400")

    def test_media_route_rejects_path_traversal(self):
        response = self.client.get("/media/../manage.py")

        self.assertEqual(response.status_code, 404)


class ProductGalleryTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Nuts", slug="nuts")
        self.product = Product.objects.create(
            category=category,
            name="Almonds",
            slug="almonds",
            short_description="Crunchy almonds",
            description="Freshly packed almonds.",
            price=Decimal("100.00"),
            static_image_path="product-images/almonds/california-almonds-main.webp",
        )
        ProductImage.objects.create(
            product=self.product,
            static_image_path="product-images/almonds/california-almonds-side.webp",
            alt_text="Side view of almonds",
            position=1,
        )

    def test_product_detail_renders_selectable_gallery_below_purchase_controls(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-product-gallery")
        self.assertContains(response, "data-gallery-image")
        self.assertContains(response, "product-gallery-thumbnails")
        self.assertContains(response, "product-images/almonds/california-almonds-side.webp")
        self.assertContains(response, "product-images/almonds/california-almonds-main.webp")


class ProductReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reviewer@example.com",
            email="reviewer@example.com",
            first_name="Priya",
            password="test-password",
        )
        self.client.force_login(self.user)
        category = Category.objects.create(name="Nuts", slug="nuts")
        self.product = Product.objects.create(
            category=category,
            name="Almonds",
            slug="almonds",
            short_description="Crunchy almonds",
            description="Freshly packed almonds.",
            price=Decimal("100.00"),
        )

    def order_item(self, status):
        order = Order.objects.create(
            user=self.user,
            status=status,
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        return OrderItem.objects.create(
            order=order,
            product=self.product,
            product_name=self.product.name,
            unit_price=self.product.price,
            quantity=1,
        )

    def test_customer_cannot_review_before_delivery(self):
        order_item = self.order_item(Order.Status.CONFIRMED)

        response = self.client.post(
            reverse("order_item_review_create", args=[order_item.order.number, order_item.id]),
            {"rating": 5, "title": "Great", "body": "Very fresh."},
        )

        self.assertRedirects(response, reverse("order_confirmation", args=[order_item.order.number]))
        self.assertFalse(ProductReview.objects.exists())

    def test_delivered_purchaser_can_leave_a_visible_review(self):
        order_item = self.order_item(Order.Status.DELIVERED)
        order_page = self.client.get(reverse("order_confirmation", args=[order_item.order.number]))
        self.assertContains(order_page, "Rate and review this product")

        order_page = self.client.get(
            f"{reverse('order_confirmation', args=[order_item.order.number])}?review={order_item.id}"
        )
        self.assertContains(order_page, f"Rate {self.product.name}")

        response = self.client.post(
            reverse("order_item_review_create", args=[order_item.order.number, order_item.id]),
            {"rating": 5, "title": "Great", "body": "Very fresh."},
        )

        self.assertRedirects(response, reverse("order_confirmation", args=[order_item.order.number]))
        review = ProductReview.objects.get()
        self.assertEqual(review.order_item, order_item)
        self.assertEqual(review.user, self.user)
        self.assertTrue(review.is_visible)
        detail = self.client.get(self.product.get_absolute_url())
        self.assertContains(detail, "Ratings &amp; reviews")
        self.assertContains(detail, "Very fresh.")
        self.assertContains(detail, "Verified purchase")
        self.assertNotContains(detail, "How was your purchase?")

        duplicate = self.client.post(
            reverse("order_item_review_create", args=[order_item.order.number, order_item.id]),
            {"rating": 4, "title": "Again", "body": "Second review."},
        )
        self.assertRedirects(duplicate, reverse("order_confirmation", args=[order_item.order.number]))
        self.assertEqual(ProductReview.objects.count(), 1)


@override_settings(
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    RAZORPAY_KEY_ID="rzp_test_example",
    RAZORPAY_KEY_SECRET="secret",
    RAZORPAY_WEBHOOK_SECRET="webhook-secret",
)
class CheckoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="buyer", password="test-password")
        self.client.force_login(self.user)
        category = Category.objects.create(name="Nuts", slug="nuts")
        self.product = Product.objects.create(category=category, name="Almonds", slug="almonds", short_description="Almonds", description="Almonds", price=Decimal("100.00"))
        self.cart = [{"id": str(self.product.id), "name": "Almonds", "price": 50, "quantity": 2}]
        self.address = {"full_name": "Test Buyer", "phone": "9876543210", "line1": "First street", "line2": "", "city": "Hyderabad", "state": "Telangana", "pincode": "500090"}

    def review(self, cart=None):
        return self.client.post(reverse("cart_review"), {"cart_payload": json.dumps(self.cart if cart is None else cart)})

    def order_data(self, quote, checkout_id=None, cart=None):
        return {**self.address, "cart_payload": json.dumps(self.cart if cart is None else cart), "cart_quote": quote, "checkout_id": str(checkout_id or uuid.uuid4())}

    def test_checkout_template_renders(self):
        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "checkout.js")
        self.assertContains(response, 'name="checkout_id"')

    def test_guest_cart_merges_with_account_cart_without_doubling_matching_items(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        response = self.client.post(reverse("cart_merge"), {"cart_payload": json.dumps([{ "id": self.product.id, "quantity": 1 }])})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["quantity"], 2)
        cart.refresh_from_db()
        self.assertEqual(cart.items.get(product=self.product).quantity, 2)

    def test_authenticated_cart_mutation_rejects_stale_version_without_losing_items(self):
        initial = self.client.post(reverse("cart_merge"), {"cart_payload": "[]"}).json()
        first = self.client.post(reverse("cart_mutate"), {"action": "add", "product_id": self.product.id, "quantity": 0, "version": initial["version"]})
        self.assertEqual(first.status_code, 200)
        stale = self.client.post(reverse("cart_mutate"), {"action": "set", "product_id": self.product.id, "quantity": 0, "version": initial["version"]})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["items"][0]["quantity"], 1)

    def test_checkout_cart_cleanup_preserves_later_added_quantity(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=3)
        carts.remove_checked_out_quantities(self.user, {(self.product.id, None): 2})
        self.assertEqual(cart.items.get(product=self.product).quantity, 1)

    def test_review_uses_database_price_and_total(self):
        response = self.review()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["price"], "100.00")
        self.assertEqual(response.json()["total"], "200.00")

    def test_variant_price_is_revalidated_and_saved_on_order(self):
        variant = ProductVariant.objects.create(product=self.product, name="500 g", price=Decimal("240.00"), shipping_weight_kg=Decimal("0.500"), is_default=True)
        cart = [{"id": f"{self.product.id}:v{variant.id}", "name": "Almonds — 500 g", "price": 1, "quantity": 2}]
        review = self.review(cart)
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["total"], "480.00")
        with patch("store.views.delivery_estimate", return_value={"message": "To be confirmed", "courier": ""}):
            result = self.client.post(reverse("checkout"), self.order_data(review.json()["quote"], cart=cart))
        self.assertEqual(result.status_code, 302)
        item = Order.objects.get().items.get()
        self.assertEqual(item.variant, variant)
        self.assertEqual(item.variant_name, "500 g")
        self.assertEqual(item.unit_price, Decimal("240.00"))

    def test_variant_must_belong_to_the_selected_product(self):
        other = Product.objects.create(category=self.product.category, name="Cashews", slug="cashews", short_description="Cashews", description="Cashews", price=Decimal("200.00"))
        variant = ProductVariant.objects.create(product=other, name="250 g", price=Decimal("220.00"))
        cart = [{"id": f"{self.product.id}:v{variant.id}", "quantity": 1}]

        response = self.review(cart)

        self.assertEqual(response.status_code, 409)
        self.assertIn("no longer available", response.json()["detail"])

    def test_inactive_variant_cannot_be_reviewed_or_purchased(self):
        variant = ProductVariant.objects.create(product=self.product, name="1 kg", price=Decimal("400.00"), is_active=False)
        cart = [{"id": f"{self.product.id}:v{variant.id}", "quantity": 1}]

        response = self.review(cart)

        self.assertEqual(response.status_code, 409)
        self.assertIn("no longer available", response.json()["detail"])

    def test_first_paid_order_coupon_is_server_validated_and_saved_on_order(self):
        Coupon.objects.create(
            code="welcome10",
            discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            maximum_discount=Decimal("100.00"),
            minimum_order_value=Decimal("150.00"),
            first_paid_order_only=True,
        )
        response = self.client.post(reverse("cart_review"), {"cart_payload": json.dumps(self.cart), "coupon_code": " welcome10 "})
        self.assertEqual(response.status_code, 200)
        quote = response.json()["quote"]
        self.assertEqual(response.json()["subtotal"], "200.00")
        self.assertEqual(response.json()["discount"], "20.00")
        self.assertEqual(response.json()["total"], "180.00")
        with patch("store.views.delivery_estimate", return_value={"message": "To be confirmed", "courier": ""}):
            result = self.client.post(reverse("checkout"), self.order_data(quote))
        self.assertEqual(result.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.coupon_code, "WELCOME10")
        self.assertEqual(order.discount_total, Decimal("20.00"))
        self.assertEqual(order.total, Decimal("180.00"))

    def test_first_paid_order_coupon_is_not_available_after_a_paid_order(self):
        Coupon.objects.create(code="WELCOME10", discount_value=Decimal("10.00"), first_paid_order_only=True)
        prior = Order.objects.create(user=self.user, subtotal=Decimal("10.00"), total=Decimal("10.00"))
        Payment.objects.create(order=prior, status=Payment.Status.PAID)
        response = self.client.post(reverse("cart_review"), {"cart_payload": json.dumps(self.cart), "coupon_code": "WELCOME10"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["coupon_error"])
        self.assertIn("first successfully paid order", response.json()["detail"])

    def test_active_public_coupon_is_shown_to_a_new_customer_only(self):
        coupon = Coupon.objects.create(
            code="WELCOME10",
            discount_value=Decimal("10.00"),
            first_paid_order_only=True,
            show_on_storefront=True,
            storefront_message="Welcome to Harvi's Delights",
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Welcome to Harvi's Delights")
        self.assertContains(response, "WELCOME10")

        prior = Order.objects.create(user=self.user, subtotal=Decimal("10.00"), total=Decimal("10.00"))
        Payment.objects.create(order=prior, status=Payment.Status.PAID)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, coupon.code)

    def test_unavailable_items_are_not_silently_omitted(self):
        cart = self.cart + [{"id": 999999, "quantity": 1, "name": "Missing"}]
        response = self.review(cart)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["unavailable_ids"], [999999])
        self.assertNotIn("quote", response.json())
        quote = self.review().json()["quote"]
        response = self.client.post(reverse("checkout"), self.order_data(quote, cart=cart))
        self.assertContains(response, "Your cart or prices changed")
        self.assertFalse(Order.objects.exists())

    def test_price_change_after_review_requires_new_review(self):
        quote = self.review().json()["quote"]
        self.product.price = Decimal("120.00")
        self.product.save()
        response = self.client.post(reverse("checkout"), self.order_data(quote))
        self.assertContains(response, "Your cart or prices changed")
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.review().json()["total"], "240.00")

    def test_item_deactivated_after_review_cannot_be_ordered(self):
        quote = self.review().json()["quote"]
        self.product.is_active = False
        self.product.save()
        response = self.client.post(reverse("checkout"), self.order_data(quote))
        self.assertContains(response, "Your cart or prices changed")
        self.assertFalse(Order.objects.exists())

    def test_changed_quantity_and_tampered_quote_are_rejected(self):
        quote = self.review().json()["quote"]
        changed = [{**self.cart[0], "quantity": 3}]
        self.assertContains(self.client.post(reverse("checkout"), self.order_data(quote, cart=changed)), "Your cart or prices changed")
        self.assertContains(self.client.post(reverse("checkout"), self.order_data(quote + "invalid")), "review is missing or expired")
        self.assertFalse(Order.objects.exists())

    @patch("store.views.delivery_estimate", return_value={"message": "To be confirmed", "courier": ""})
    def test_retry_returns_original_order_without_duplicates(self, _estimate):
        quote = self.review().json()["quote"]
        data = self.order_data(quote)
        first = self.client.post(reverse("checkout"), data)
        second = self.client.post(reverse("checkout"), data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(first.url, second.url)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(CustomerAddress.objects.count(), 1)
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("200.00"))
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.environment, Order.Environment.TEST)
        self.assertEqual(order.items.get().unit_price, Decimal("100.00"))

    @patch("store.views.delivery_estimate", return_value={"message": "To be confirmed", "courier": ""})
    def test_confirmation_only_clears_matching_pending_cart(self, _estimate):
        response = self.client.post(reverse("checkout"), self.order_data(self.review().json()["quote"]))
        confirmation = self.client.get(response.url)
        self.assertContains(confirmation, "sessionStorage.getItem(marker)")
        self.assertContains(confirmation, "localStorage.getItem('harvis-cart') === submitted")
        self.assertContains(confirmation, str(Order.objects.get().checkout_id))

    def test_invalid_cart_and_missing_quote_are_rejected(self):
        self.assertEqual(self.review([{"id": self.product.id, "quantity": 21}]).status_code, 400)
        self.assertEqual(self.review(self.cart * 2).status_code, 400)
        response = self.client.post(reverse("checkout"), self.order_data(""))
        self.assertContains(response, "review is missing or expired")
        self.assertFalse(Order.objects.exists())

    @override_settings(ZEPTOMAIL_API_URL="https://api.zeptomail.com/v1.1/email", ZEPTOMAIL_API_KEY="key", EMAIL_BACKEND="store.services.zeptomail.ZeptoMailBackend")
    @patch("store.services.zeptomail.requests.post", side_effect=ConnectionError("offline"))
    @patch("store.views.delivery_estimate", return_value={"message": "To be confirmed", "courier": ""})
    def test_order_is_saved_once_even_when_email_fails(self, _estimate, _post):
        self.user.email = "buyer@example.com"
        self.user.save()
        data = self.order_data(self.review().json()["quote"])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("checkout"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderEmail.objects.filter(status="failed").count(), 2)
        self.client.post(reverse("checkout"), data)
        self.assertEqual(OrderEmail.objects.count(), 2)
