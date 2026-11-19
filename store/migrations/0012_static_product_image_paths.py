from django.db import migrations, models
import store.models


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0011_remove_order_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="static_image_path",
            field=models.CharField(
                blank=True,
                help_text="Optional Git-managed image path, e.g. product-images/almonds/california-almonds-main.webp. Takes priority over the uploaded image.",
                max_length=255,
                validators=[store.models.validate_static_product_image_path],
            ),
        ),
        migrations.AlterField(
            model_name="productimage",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="products/gallery/"),
        ),
        migrations.AddField(
            model_name="productimage",
            name="static_image_path",
            field=models.CharField(
                blank=True,
                help_text="Optional Git-managed image path under product-images/. Takes priority over the uploaded image.",
                max_length=255,
                validators=[store.models.validate_static_product_image_path],
            ),
        ),
    ]
