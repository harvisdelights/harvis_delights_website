from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0009_alter_order_environment_alter_payment_environment"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderemail",
            name="deduplication_key",
            field=models.CharField(blank=True, editable=False, max_length=180, null=True, unique=True),
        ),
    ]
