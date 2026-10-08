from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="api-product")
router.register("categories", views.CategoryViewSet, basename="api-category")
urlpatterns = [path("", views.home, name="home"), path("products/", views.products, name="products"), path("products/<slug:slug>/", views.product_detail, name="product_detail"), path("api/", include(router.urls))]
