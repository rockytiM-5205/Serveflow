"""The OpenAPI schema is generated from the real views."""
import pytest
from django.core.management import call_command
from django.urls import reverse


@pytest.mark.django_db
def test_schema_generates_without_warnings(tmp_path):
    target = tmp_path / "schema.yml"
    call_command("spectacular", file=str(target), fail_on_warn=True)
    text = target.read_text()
    for path in (
        "/api/v1/auth/login/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/me/",
        "/api/v1/auth/csrf/",
        "/api/v1/restaurants/{slug}/members/",
        "/api/v1/restaurants/{slug}/",
        "/api/v1/restaurants/{slug}/menu/",
        "/api/v1/restaurants/{slug}/menu/categories/",
        "/api/v1/restaurants/{slug}/menu/items/{id}/archive/",
        "/api/v1/restaurants/{slug}/menu/items/{id}/availability/",
        "/api/v1/restaurants/{slug}/audit/",
        "/api/v1/auth/signup/",
        "/api/v1/auth/password/",
        "/api/v1/auth/options/",
        "/api/v1/restaurants/{slug}/settings/",
        "/api/v1/restaurants/{slug}/members/{id}/",
        "/api/v1/restaurants/{slug}/orders/",
        "/api/v1/restaurants/{slug}/orders/{public_id}/",
        "/api/v1/restaurants/{slug}/orders/{public_id}/transitions/",
        "/api/v1/restaurants/{slug}/orders/{public_id}/cancel/",
        "/api/v1/restaurants/{slug}/orders/{public_id}/payment/",
        "/api/v1/orders/{token}/",
        "/api/v1/orders/{token}/cancel/",
    ):
        assert path in text


@pytest.mark.django_db
def test_schema_endpoint_is_served(client):
    assert client.get(reverse("schema")).status_code == 200
