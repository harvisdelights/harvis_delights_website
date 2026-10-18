from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0006_payment")]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="environment",
            field=models.CharField(choices=[("legacy", "Legacy / unverified"), ("test", "Test")], default="legacy", editable=False, max_length=12),
        ),
    ]
