from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("store", "0001_initial")]
    operations = [
        migrations.AddField(model_name="product", name="flipkart_url", field=models.URLField(blank=True, help_text="Optional product listing URL on Flipkart")),
        migrations.AddField(model_name="product", name="meesho_url", field=models.URLField(blank=True, help_text="Optional product listing URL on Meesho")),
    ]
