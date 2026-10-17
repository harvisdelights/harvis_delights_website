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
    path("password-recovery/", views.CustomerPasswordResetView.as_view(), name="password_recovery"),
    path("password-recovery/done/", views.CustomerPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", views.CustomerPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password-reset/complete/", views.CustomerPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("password-change/", views.CustomerPasswordChangeView.as_view(), name="password_change"),
    path("checkout/", views.checkout, name="checkout"),
    path("cart-review/", views.cart_review, name="cart_review"),
    path("shipping-estimate/", views.shipping_estimate, name="shipping_estimate"),
    path("orders/<str:number>/", views.order_confirmation, name="order_confirmation"),
    path("orders/<str:number>/payment/start/", views.payment_start, name="payment_start"),
    path("orders/<str:number>/payment/verify/", views.payment_verify, name="payment_verify"),
    path("payments/razorpay/webhook/", views.razorpay_webhook, name="razorpay_webhook"),
    path("products/", views.products, name="products"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("api/", include(router.urls)),
]
