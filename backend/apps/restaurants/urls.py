"""Staff routes, mounted at /api/v1/restaurants/<slug>/. Every view here must inherit
RestaurantScopedMixin (a test enforces it)."""
from django.urls import path

from . import views

urlpatterns = [
    path("members/", views.MemberListView.as_view(), name="restaurant-members"),
    path("members/<int:pk>/", views.MemberDetailView.as_view(), name="restaurant-member"),
    path("settings/", views.RestaurantSettingsView.as_view(), name="restaurant-settings"),
]
