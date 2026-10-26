"""Tenant isolation and role checks, using the members endpoint. Need PostgreSQL and the migrations."""
from types import SimpleNamespace

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from apps.audit import urls as audit_urls
from apps.menu import urls as menu_urls
from apps.orders import urls as order_urls
from apps.restaurants import urls as restaurant_urls
from apps.restaurants.models import MembershipRole
from apps.restaurants.permissions import ROLE_RANK, HasRestaurantRole, RestaurantScopedMixin

pytestmark = pytest.mark.django_db


def members_url(slug):
    return reverse("restaurant-members", kwargs={"slug": slug})


def error_code(response):
    return response.json()["error"]["code"]


def test_anonymous_gets_401(api_client, make_restaurant):
    response = api_client.get(members_url(make_restaurant().slug))
    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"


def test_non_member_gets_403(api_client, make_user, make_restaurant):
    api_client.force_login(make_user())
    response = api_client.get(members_url(make_restaurant().slug))
    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


def test_unknown_slug_looks_the_same_as_non_membership(api_client, make_user):
    api_client.force_login(make_user())
    response = api_client.get(members_url("does-not-exist"))
    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


def test_staff_role_is_not_enough(api_client, make_user, make_restaurant, make_membership):
    restaurant, user = make_restaurant(), make_user()
    make_membership(restaurant, user, MembershipRole.STAFF)
    api_client.force_login(user)
    response = api_client.get(members_url(restaurant.slug))
    assert response.status_code == 403
    assert error_code(response) == "insufficient_role"


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.OWNER])
def test_manager_and_owner_can_list_members(api_client, make_user, make_restaurant, make_membership, role):
    restaurant, user = make_restaurant(), make_user()
    make_membership(restaurant, user, role)
    api_client.force_login(user)
    assert api_client.get(members_url(restaurant.slug)).status_code == 200


def test_manager_of_one_restaurant_cannot_use_anothers_slug(
    api_client, make_user, make_restaurant, make_membership
):
    mine, other = make_restaurant(), make_restaurant()
    manager = make_user()
    make_membership(mine, manager, MembershipRole.MANAGER)
    make_membership(other, make_user(), MembershipRole.OWNER)
    api_client.force_login(manager)

    response = api_client.get(members_url(other.slug))

    assert response.status_code == 403
    assert error_code(response) == "not_a_member"


def test_manager_sees_only_their_restaurants_members(
    api_client, make_user, make_restaurant, make_membership
):
    mine, other = make_restaurant(), make_restaurant()
    manager, colleague, stranger = make_user(), make_user(), make_user()
    make_membership(mine, manager, MembershipRole.MANAGER)
    make_membership(mine, colleague)
    make_membership(other, stranger, MembershipRole.OWNER)
    api_client.force_login(manager)

    body = api_client.get(members_url(mine.slug)).json()

    emails = {m["user"]["email"] for m in body["results"]}
    assert emails == {manager.email, colleague.email}
    assert set(body) == {"next", "previous", "results"}


def test_member_payload_exposes_no_secrets(api_client, make_user, make_restaurant, make_membership):
    restaurant, manager = make_restaurant(), make_user()
    make_membership(restaurant, manager, MembershipRole.MANAGER)
    api_client.force_login(manager)

    member = api_client.get(members_url(restaurant.slug)).json()["results"][0]

    assert set(member) == {"id", "user", "role", "is_active", "created_at"}
    assert set(member["user"]) == {"id", "email", "first_name", "last_name"}


def test_deactivated_membership_loses_access_on_the_next_request(
    api_client, make_user, make_restaurant, make_membership
):
    restaurant, user = make_restaurant(), make_user()
    membership = make_membership(restaurant, user, MembershipRole.MANAGER)
    api_client.force_login(user)
    assert api_client.get(members_url(restaurant.slug)).status_code == 200

    membership.is_active = False
    membership.save()

    assert api_client.get(members_url(restaurant.slug)).status_code == 403


def test_suspended_restaurant_blocks_staff(api_client, make_user, make_restaurant, make_membership):
    restaurant, user = make_restaurant(is_active=False), make_user()
    make_membership(restaurant, user, MembershipRole.OWNER)
    api_client.force_login(user)
    assert api_client.get(members_url(restaurant.slug)).status_code == 403


def test_deactivated_user_session_is_rejected(api_client, make_user, make_restaurant, make_membership):
    restaurant, user = make_restaurant(), make_user()
    make_membership(restaurant, user, MembershipRole.OWNER)
    api_client.force_login(user)
    user.is_active = False
    user.save()
    assert api_client.get(members_url(restaurant.slug)).status_code == 401


def test_every_restaurant_scoped_view_uses_the_tenant_base():
    patterns = [*restaurant_urls.urlpatterns, *menu_urls.urlpatterns, *audit_urls.urlpatterns, *order_urls.urlpatterns]
    assert patterns
    for pattern in patterns:
        view_class = pattern.callback.view_class
        assert issubclass(view_class, RestaurantScopedMixin), view_class
        assert view_class.min_role in ROLE_RANK, view_class
        assert all(role in ROLE_RANK for role in view_class.min_roles.values()), view_class
        assert HasRestaurantRole in view_class.permission_classes, view_class


def test_a_staff_view_without_min_role_fails_closed():
    view = SimpleNamespace(min_role=None, kwargs={"slug": "x"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
    with pytest.raises(ImproperlyConfigured):
        HasRestaurantRole().has_permission(request, view)


def test_unknown_api_paths_return_the_json_envelope(api_client):
    response = api_client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert error_code(response) == "not_found"
