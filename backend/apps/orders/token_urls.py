"""Customer routes under /api/v1/orders/. The token in the path is the credential."""
from django.urls import path

from . import public_views

urlpatterns = [
    path("<str:token>/", public_views.PublicOrderView.as_view(), name="public-order"),
    path("<str:token>/cancel/", public_views.PublicOrderCancelView.as_view(), name="public-order-cancel"),
]
