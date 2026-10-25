from django.contrib import admin
from django.urls import include, path
from store import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health),
    # Product uploads live on the Render persistent disk. This route must be
    # registered in production too; django.conf.urls.static() is DEBUG-only.
    path("media/<path:path>", views.product_media, name="product_media"),
    path("", include("store.urls")),
]
