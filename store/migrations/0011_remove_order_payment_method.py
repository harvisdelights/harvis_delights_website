from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0010_orderemail_deduplication_key"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="payment_method",
        ),
    ]
