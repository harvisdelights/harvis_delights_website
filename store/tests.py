import json
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, CustomerAddress, Order, Product


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
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

    def test_review_uses_database_price_and_total(self):
        response = self.review()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["price"], "100.00")
        self.assertEqual(response.json()["total"], "200.00")

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
