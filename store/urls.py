from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views
router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="api-product")
router.register("categories", views.CategoryViewSet, basename="api-category")
urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.customer_login, name="login"),
    path("signup/", views.signup, name="signup"),
    path("logout/", views.customer_logout, name="logout"),
    path("account/", views.account, name="account"),
    path("password-recovery/", views.password_recovery, name="password_recovery"),
    path("password-change/", views.CustomerPasswordChangeView.as_view(), name="password_change"),
    path("checkout/", views.checkout, name="checkout"),
    path("shipping-estimate/", views.shipping_estimate, name="shipping_estimate"),
    path("orders/<str:number>/", views.order_confirmation, name="order_confirmation"),
    path("products/", views.products, name="products"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("api/", include(router.urls)),
]
