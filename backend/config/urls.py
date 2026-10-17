"""Root URL configuration. API routes under /api/v1/ are added in later stages."""
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
