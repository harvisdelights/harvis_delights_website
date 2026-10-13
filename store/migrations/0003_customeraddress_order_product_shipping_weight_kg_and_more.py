import django.conf
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(django.conf.settings.AUTH_USER_MODEL),
        ("store", "0002_product_marketplace_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="shipping_weight_kg",
            field=models.DecimalField(decimal_places=3, default=0.5, help_text="Used for delivery estimates.", max_digits=5),
        ),
        migrations.CreateModel(
            name="CustomerAddress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=120)), ("phone", models.CharField(max_length=15)),
                ("line1", models.CharField(max_length=180, verbose_name="Address line 1")), ("line2", models.CharField(blank=True, max_length=180, verbose_name="Address line 2")),
                ("city", models.CharField(max_length=80)), ("state", models.CharField(max_length=80)), ("pincode", models.CharField(max_length=6)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="addresses", to=django.conf.settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("number", models.CharField(editable=False, max_length=28, unique=True)),
                ("status", models.CharField(choices=[("pending", "Pending confirmation"), ("confirmed", "Confirmed"), ("packed", "Packed"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="pending", max_length=12)),
                ("payment_method", models.CharField(default="pay_on_confirmation", max_length=24)), ("subtotal", models.DecimalField(decimal_places=2, max_digits=10)),
                ("shipping_charge", models.DecimalField(decimal_places=2, default=0, max_digits=10)), ("total", models.DecimalField(decimal_places=2, max_digits=10)),
                ("delivery_estimate", models.CharField(blank=True, max_length=160)), ("shiprocket_courier", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("address", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="store.customeraddress")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="orders", to=django.conf.settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("product_name", models.CharField(max_length=160)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)), ("quantity", models.PositiveIntegerField()),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="store.order")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="order_items", to="store.product")),
            ],
        ),
    ]
