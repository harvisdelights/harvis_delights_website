from rest_framework import serializers
from .models import Category, Product, ProductImage

class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.ReadOnlyField(source="display_image_url")
    class Meta: model = ProductImage; fields = ("id", "image", "static_image_path", "image_url", "alt_text", "position")
class CategorySerializer(serializers.ModelSerializer):
    class Meta: model = Category; fields = ("id", "name", "slug")
class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    gallery = ProductImageSerializer(many=True, read_only=True)
    image_url = serializers.ReadOnlyField(source="display_image_url")
    class Meta:
        model = Product
        fields = ("id", "name", "slug", "short_description", "description", "price", "weight", "image", "static_image_path", "image_url", "flipkart_url", "meesho_url", "is_featured", "category", "gallery")
