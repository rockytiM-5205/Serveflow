"""Public routes under /api/v1/restaurants/<slug>/. No authentication."""
from django.urls import path

from . import views

urlpatterns = [
    path("menu/", views.PublicMenuView.as_view(), name="public-menu"),
]
