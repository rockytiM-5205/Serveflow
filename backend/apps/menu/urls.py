"""Staff routes under /api/v1/restaurants/<slug>/ (must all use RestaurantScopedMixin)."""
from django.urls import path

from . import views

urlpatterns = [
    path("menu/categories/", views.CategoryListCreateView.as_view(), name="staff-menu-categories"),
    path("menu/categories/<int:pk>/", views.CategoryDetailView.as_view(), name="staff-menu-category"),
    path("menu/items/", views.ItemListCreateView.as_view(), name="staff-menu-items"),
    path("menu/items/<int:pk>/", views.ItemDetailView.as_view(), name="staff-menu-item"),
    path("menu/items/<int:pk>/archive/", views.ItemArchiveView.as_view(), name="staff-menu-item-archive"),
    path("menu/items/<int:pk>/availability/", views.ItemAvailabilityView.as_view(), name="staff-menu-item-availability"),
]
