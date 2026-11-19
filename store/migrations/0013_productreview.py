from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0012_static_product_image_paths"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])),
                ("title", models.CharField(blank=True, max_length=120)),
                ("body", models.TextField(max_length=2000)),
                ("is_visible", models.BooleanField(default=True, help_text="Hidden reviews are retained but are not shown to customers.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order_item", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="review", to="store.orderitem")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="store.product")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="product_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
