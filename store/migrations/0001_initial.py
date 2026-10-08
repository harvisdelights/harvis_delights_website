from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name='Category', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('name', models.CharField(max_length=80, unique=True)), ('slug', models.SlugField(unique=True))]),
        migrations.CreateModel(name='Product', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('name', models.CharField(max_length=160)), ('slug', models.SlugField(unique=True)), ('short_description', models.CharField(max_length=220)), ('description', models.TextField()), ('price', models.DecimalField(decimal_places=2, max_digits=10)), ('weight', models.CharField(blank=True, max_length=40)), ('image', models.ImageField(blank=True, null=True, upload_to='products/')), ('is_featured', models.BooleanField(default=False)), ('is_active', models.BooleanField(default=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)), ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='store.category'))], options={'ordering': ['-is_featured', 'name']}),
        migrations.CreateModel(name='ProductImage', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('image', models.ImageField(upload_to='products/gallery/')), ('alt_text', models.CharField(blank=True, max_length=140)), ('position', models.PositiveIntegerField(default=0)), ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gallery', to='store.product'))], options={'ordering': ['position', 'id']}),
    ]
