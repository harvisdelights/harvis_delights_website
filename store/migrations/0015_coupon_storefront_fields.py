from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0014_coupon_order_coupon_fields_couponredemption")]

    operations = [
        migrations.AddField(
            model_name="coupon",
            name="show_on_storefront",
            field=models.BooleanField(default=False, help_text="Show this promotion in the public announcement bar when it is active."),
        ),
        migrations.AddField(
            model_name="coupon",
            name="storefront_message",
            field=models.CharField(blank=True, help_text="Optional customer-facing promotion message. The code and terms are added automatically.", max_length=180),
        ),
        migrations.AddField(
            model_name="coupon",
            name="storefront_priority",
            field=models.PositiveSmallIntegerField(default=0, help_text="Higher-priority promotions are shown first. Only one is displayed."),
        ),
    ]
