from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0003_customeraddress_order_product_shipping_weight_kg_and_more")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="checkout_id",
            field=models.UUIDField(editable=False, null=True, unique=True),
        ),
    ]
