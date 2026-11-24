from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("store", "0016_cart_cartitem")]

    operations = [
        migrations.CreateModel(
            name="ProductVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Customer-facing option, for example 250 g or 1 kg.", max_length=60)),
                ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("shipping_weight_kg", models.DecimalField(blank=True, decimal_places=3, help_text="Optional override for delivery estimates. Leave empty to use the product weight.", max_digits=5, null=True)),
                ("sku", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("is_default", models.BooleanField(default=False, help_text="Preselected on the product page when more than one option is available.")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="store.product")),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(fields=("product", "name"), name="unique_variant_name_per_product"),
        ),
        migrations.RemoveConstraint(model_name="cartitem", name="unique_product_per_cart"),
        migrations.AddField(
            model_name="cartitem",
            name="variant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="cart_items", to="store.productvariant"),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.UniqueConstraint(condition=Q(variant__isnull=False), fields=("cart", "variant"), name="unique_variant_per_cart"),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.UniqueConstraint(condition=Q(variant__isnull=True), fields=("cart", "product"), name="unique_base_product_per_cart"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="variant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="order_items", to="store.productvariant"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="variant_name",
            field=models.CharField(blank=True, editable=False, max_length=60),
        ),
    ]
