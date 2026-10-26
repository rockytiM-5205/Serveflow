"""Staff routes under /api/v1/restaurants/<slug>/ (must all use RestaurantScopedMixin)."""
from django.urls import path

from . import views

urlpatterns = [
    path("audit/", views.AuditLogListView.as_view(), name="staff-audit"),
]
