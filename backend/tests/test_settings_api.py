"""Restaurant settings endpoint."""
import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.restaurants.models import MembershipRole

pytestmark = pytest.mark.django_db

STAFF, MANAGER, OWNER = MembershipRole.STAFF, MembershipRole.MANAGER, MembershipRole.OWNER


def url(restaurant):
    return reverse("restaurant-settings", kwargs={"slug": restaurant.slug})


def test_any_staff_role_can_read_settings(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant(description="Hello")
    staff_login(restaurant, STAFF)
    body = api_client.get(url(restaurant)).json()
    assert body["slug"] == restaurant.slug and body["description"] == "Hello" and body["accepting_orders"] is False


def test_staff_can_pause_and_resume_orders_but_nothing_else(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, STAFF)
    assert api_client.patch(url(restaurant), {"accepting_orders": True}, format="json").status_code == 200
    restaurant.refresh_from_db()
    assert restaurant.accepting_orders is True

    refused = api_client.patch(url(restaurant), {"accepting_orders": False, "name": "Hacked"}, format="json")
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "insufficient_role"
    restaurant.refresh_from_db()
    assert restaurant.name != "Hacked" and restaurant.accepting_orders is True


def test_manager_edits_details_and_the_change_is_audited(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    user = staff_login(restaurant, MANAGER)
    response = api_client.patch(url(restaurant), {"name": "New Name", "currency": "eur"}, format="json")
    assert response.status_code == 200
    restaurant.refresh_from_db()
    assert restaurant.name == "New Name" and restaurant.currency == "EUR"
    entry = AuditLog.objects.get()
    assert (entry.action, entry.actor) == ("restaurant.settings_changed", user)
    assert entry.metadata == {"changed": ["currency", "name"]}


def test_slug_cannot_be_changed(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant(slug="original")
    staff_login(restaurant, OWNER)
    api_client.patch(url(restaurant), {"slug": "different"}, format="json")
    restaurant.refresh_from_db()
    assert restaurant.slug == "original"


def test_settings_keep_fulfilment_rules(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()  # pickup only
    staff_login(restaurant, MANAGER)
    assert api_client.patch(url(restaurant), {"requires_table_number": True}, format="json").status_code == 400
    assert api_client.patch(url(restaurant), {"pickup_enabled": False}, format="json").status_code == 400
    ok = api_client.patch(url(restaurant), {"dine_in_enabled": True, "requires_table_number": True}, format="json")
    assert ok.status_code == 200


def test_settings_are_tenant_scoped(api_client, make_restaurant, make_user, make_membership):
    mine, other = make_restaurant(), make_restaurant()
    user = make_user()
    make_membership(mine, user, OWNER)
    api_client.force_login(user)
    assert api_client.get(url(other)).status_code == 403
    assert api_client.patch(url(other), {"name": "x"}, format="json").status_code == 403


def test_settings_require_sign_in(api_client, make_restaurant):
    assert api_client.get(url(make_restaurant())).status_code == 401
