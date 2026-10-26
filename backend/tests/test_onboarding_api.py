"""Self-service sign-up, restaurant creation and password change. Need PostgreSQL and the migrations."""
import pytest
from django.contrib.auth import authenticate, get_user_model
from django.urls import reverse

from apps.restaurants.models import MembershipRole, Restaurant, RestaurantMembership

PASSWORD = "s3cret-pass-123"  # same value the conftest factory uses

pytestmark = pytest.mark.django_db

GOOD = {"name": "Green Bowl", "slug": "green-bowl", "currency": "usd", "timezone": "Europe/London"}


def code(response):
    return response.json()["error"]["code"]


def signup(client, **overrides):
    body = {"email": "New@Example.com", "password": "a-long-unusual-pass-9", "first_name": "Ada", **overrides}
    return client.post(reverse("auth-signup"), body, format="json")


# ---------------------------------------------------------------- options and signup
@pytest.mark.parametrize("enabled", [True, False])
def test_options_report_whether_self_service_is_on(api_client, settings, enabled):
    settings.SELF_SERVICE = enabled
    assert api_client.get(reverse("auth-options")).json() == {"self_service": enabled}


def test_signup_is_refused_when_self_service_is_off(api_client, settings):
    settings.SELF_SERVICE = False
    response = signup(api_client)
    assert response.status_code == 403 and code(response) == "signup_disabled"
    assert not get_user_model().objects.exists()


def test_signup_creates_an_account_and_signs_in(api_client, settings):
    settings.SELF_SERVICE = True
    response = signup(api_client)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["memberships"] == [] and body["can_create_restaurant"] is True
    user = get_user_model().objects.get()
    assert user.check_password("a-long-unusual-pass-9") and not user.is_staff and not user.is_superuser
    assert api_client.get(reverse("auth-me")).status_code == 200  # already signed in


def test_signup_rejects_duplicate_email_ignoring_case(api_client, settings, make_user):
    settings.SELF_SERVICE = True
    make_user(email="new@example.com")
    response = signup(api_client)
    assert response.status_code == 400 and "email" in response.json()["error"]["details"]


@pytest.mark.parametrize("password", ["12345678", "short", "password123"])
def test_signup_enforces_password_rules(api_client, settings, password):
    settings.SELF_SERVICE = True
    response = signup(api_client, password=password)
    assert response.status_code == 400 and "password" in response.json()["error"]["details"]


def test_signup_requires_a_csrf_token(csrf_client, settings):
    settings.SELF_SERVICE = True
    response = signup(csrf_client)
    assert response.status_code == 403 and code(response) == "csrf_failed"


def test_signup_is_throttled(api_client, settings):
    settings.SELF_SERVICE = True
    for _ in range(10):
        signup(api_client, email="bad")
    assert signup(api_client, email="bad").status_code == 429


# ---------------------------------------------------------------- password change
def test_change_password_keeps_the_session_and_replaces_the_password(api_client, make_user):
    user = make_user(email="a@example.com")
    api_client.force_login(user)
    response = api_client.post(
        reverse("auth-password"), {"current_password": PASSWORD, "new_password": "another-unusual-pass-7"}, format="json"
    )
    assert response.status_code == 204
    assert authenticate(email="a@example.com", password="another-unusual-pass-7") is not None
    assert authenticate(email="a@example.com", password=PASSWORD) is None


def test_change_password_checks_the_current_password_and_the_new_one(api_client, make_user):
    api_client.force_login(make_user())
    url = reverse("auth-password")
    wrong = api_client.post(url, {"current_password": "nope", "new_password": "another-unusual-pass-7"}, format="json")
    weak = api_client.post(url, {"current_password": PASSWORD, "new_password": "12345678"}, format="json")
    assert "current_password" in wrong.json()["error"]["details"]
    assert "new_password" in weak.json()["error"]["details"]


def test_change_password_requires_sign_in(api_client):
    assert api_client.post(reverse("auth-password"), {}, format="json").status_code == 401


# ---------------------------------------------------------------- restaurant creation
def test_creating_a_restaurant_needs_self_service_or_superuser(api_client, settings, make_user):
    settings.SELF_SERVICE = False
    api_client.force_login(make_user())
    response = api_client.post(reverse("restaurant-create"), GOOD, format="json")
    assert response.status_code == 403 and code(response) == "restaurant_creation_unavailable"


def test_superusers_can_create_restaurants_without_self_service(api_client, settings, make_user):
    settings.SELF_SERVICE = False
    api_client.force_login(make_user(is_superuser=True, is_staff=True))
    assert api_client.post(reverse("restaurant-create"), GOOD, format="json").status_code == 201


def test_creating_a_restaurant_makes_the_caller_its_owner(api_client, settings, make_user):
    settings.SELF_SERVICE = True
    user = make_user()
    api_client.force_login(user)

    response = api_client.post(reverse("restaurant-create"), GOOD, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "green-bowl" and body["currency"] == "USD" and body["accepting_orders"] is False
    restaurant = Restaurant.objects.get(slug="green-bowl")
    assert RestaurantMembership.objects.get(restaurant=restaurant, user=user).role == MembershipRole.OWNER
    me = api_client.get(reverse("auth-me")).json()
    assert [m["restaurant"]["slug"] for m in me["memberships"]] == ["green-bowl"]


@pytest.mark.parametrize(
    "override, field",
    [
        ({"slug": "admin"}, "slug"),
        ({"slug": "Has Space"}, "slug"),
        ({"slug": "ab"}, "slug"),
        ({"currency": "DOLLARS"}, "currency"),
        ({"currency": "12"}, "currency"),
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"name": ""}, "name"),
        ({"pickup_enabled": False, "dine_in_enabled": False}, "pickup_enabled"),
        ({"requires_table_number": True}, "requires_table_number"),
    ],
)
def test_restaurant_input_is_validated(api_client, settings, make_user, override, field):
    settings.SELF_SERVICE = True
    api_client.force_login(make_user())
    response = api_client.post(reverse("restaurant-create"), {**GOOD, **override}, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]
    assert not Restaurant.objects.exists()


def test_slug_must_be_unique(api_client, settings, make_user, make_restaurant):
    settings.SELF_SERVICE = True
    make_restaurant(slug="green-bowl")
    api_client.force_login(make_user())
    response = api_client.post(reverse("restaurant-create"), GOOD, format="json")
    assert response.status_code == 400 and "slug" in response.json()["error"]["details"]


def test_dine_in_with_table_numbers_is_accepted(api_client, settings, make_user):
    settings.SELF_SERVICE = True
    api_client.force_login(make_user())
    body = {**GOOD, "dine_in_enabled": True, "requires_table_number": True}
    assert api_client.post(reverse("restaurant-create"), body, format="json").status_code == 201


def test_a_user_can_own_a_limited_number_of_restaurants(api_client, settings, make_user):
    settings.SELF_SERVICE = True
    settings.MAX_RESTAURANTS_PER_USER = 2
    api_client.force_login(make_user())
    for i in range(2):
        assert api_client.post(reverse("restaurant-create"), {**GOOD, "slug": f"place-{i}"}, format="json").status_code == 201
    blocked = api_client.post(reverse("restaurant-create"), {**GOOD, "slug": "place-9"}, format="json")
    assert blocked.status_code == 403


def test_creating_a_restaurant_requires_sign_in(api_client):
    assert api_client.post(reverse("restaurant-create"), GOOD, format="json").status_code == 401
