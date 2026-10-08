from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from store import views

urlpatterns = [path("admin/", admin.site.urls), path("health/", views.health), path("", include("store.urls"))]
# Product uploads are retained on the Railway volume and served by this single-instance app.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
