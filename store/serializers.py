from rest_framework import serializers
from .models import Category, Product, ProductImage

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta: model = ProductImage; fields = ("id", "image", "alt_text", "position")
class CategorySerializer(serializers.ModelSerializer):
    class Meta: model = Category; fields = ("id", "name", "slug")
class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    gallery = ProductImageSerializer(many=True, read_only=True)
    class Meta:
        model = Product
        fields = ("id", "name", "slug", "short_description", "description", "price", "weight", "image", "flipkart_url", "meesho_url", "is_featured", "category", "gallery")
