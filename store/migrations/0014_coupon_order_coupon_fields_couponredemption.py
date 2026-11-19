from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0013_productreview"),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True)),
                ("discount_type", models.CharField(choices=[("percentage", "Percentage"), ("fixed", "Fixed amount")], default="percentage", max_length=12)),
                ("discount_value", models.DecimalField(decimal_places=2, max_digits=10)),
                ("maximum_discount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("minimum_order_value", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("first_paid_order_only", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.AddField(model_name="order", name="coupon", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="orders", to="store.coupon")),
        migrations.AddField(model_name="order", name="coupon_code", field=models.CharField(blank=True, editable=False, max_length=32)),
        migrations.AddField(model_name="order", name="discount_total", field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.CreateModel(
            name="CouponRedemption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("coupon", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="redemptions", to="store.coupon")),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="coupon_redemption", to="store.order")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="coupon_redemptions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(model_name="couponredemption", constraint=models.UniqueConstraint(fields=("coupon", "user"), name="unique_coupon_redemption_per_user")),
    ]
