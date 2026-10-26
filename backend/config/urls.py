"""Root URL configuration."""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from apps.restaurants.views import RestaurantCreateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

handler404 = "apps.common.views.not_found"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/restaurants/", RestaurantCreateView.as_view(), name="restaurant-create"),
    # Public (customer) routes first, then staff routes; both live under one slug prefix.
    path("api/v1/restaurants/<slug:slug>/", include("apps.restaurants.public_urls")),
    path("api/v1/restaurants/<slug:slug>/", include("apps.menu.public_urls")),
    path("api/v1/restaurants/<slug:slug>/", include("apps.orders.public_urls")),
    path("api/v1/orders/", include("apps.orders.token_urls")),
    path("api/v1/restaurants/<slug:slug>/", include("apps.restaurants.urls")),
    path("api/v1/restaurants/<slug:slug>/", include("apps.menu.urls")),
    path("api/v1/restaurants/<slug:slug>/", include("apps.audit.urls")),
    path("api/v1/restaurants/<slug:slug>/", include("apps.orders.urls")),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
