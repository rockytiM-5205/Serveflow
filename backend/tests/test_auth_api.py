"""Auth endpoints. Need PostgreSQL and the migrations."""
import pytest
from django.urls import reverse

from apps.restaurants.models import MembershipRole

PASSWORD = "s3cret-pass-123"  # same value the conftest factory uses

pytestmark = pytest.mark.django_db


def post_login(client, email, password=PASSWORD, **extra):
    return client.post(reverse("auth-login"), {"email": email, "password": password}, format="json", **extra)


def csrf_header(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def test_csrf_endpoint_sets_cookie(csrf_client):
    response = csrf_client.get(reverse("auth-csrf"))
    assert response.status_code == 204
    assert "csrftoken" in response.cookies


def test_login_returns_user_and_only_active_memberships(
    api_client, make_user, make_restaurant, make_membership
):
    user = make_user(email="alice@example.com", first_name="Alice")
    shown = make_restaurant()
    make_membership(shown, user, MembershipRole.MANAGER)
    make_membership(make_restaurant(), user, is_active=False)  # deactivated membership
    make_membership(make_restaurant(is_active=False), user)  # suspended restaurant

    response = post_login(api_client, "alice@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["memberships"] == [
        {"restaurant": {"slug": shown.slug, "name": shown.name}, "role": "MANAGER"}
    ]
    assert "password" not in response.content.decode()


def test_login_failures_are_indistinguishable(api_client, make_user):
    make_user(email="alice@example.com")
    wrong_password = post_login(api_client, "alice@example.com", "wrong-password")
    unknown_email = post_login(api_client, "nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "authentication_failed"
    assert "WWW-Authenticate" in wrong_password.headers


def test_inactive_user_cannot_log_in(api_client, make_user):
    make_user(email="gone@example.com", is_active=False)
    assert post_login(api_client, "gone@example.com").status_code == 401


def test_login_validates_input(api_client):
    response = post_login(api_client, "not-an-email")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "email" in error["details"]


def test_login_requires_a_csrf_token(csrf_client, make_user):
    make_user(email="alice@example.com")
    refused = post_login(csrf_client, "alice@example.com")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "csrf_failed"

    csrf_client.get(reverse("auth-csrf"))
    accepted = post_login(csrf_client, "alice@example.com", **csrf_header(csrf_client))
    assert accepted.status_code == 200


def test_session_cookie_is_http_only(api_client, make_user):
    make_user(email="alice@example.com")
    response = post_login(api_client, "alice@example.com")
    assert response.cookies["sessionid"]["httponly"]


def test_login_is_throttled_after_five_attempts(api_client, make_user):
    make_user(email="alice@example.com")
    for _ in range(5):
        assert post_login(api_client, "alice@example.com", "wrong").status_code == 401
    blocked = post_login(api_client, "alice@example.com", "wrong")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "throttled"


def test_me_requires_authentication(api_client):
    response = api_client.get(reverse("auth-me"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_returns_the_session(api_client, make_user, make_restaurant, make_membership):
    user = make_user(email="alice@example.com")
    restaurant = make_restaurant()
    make_membership(restaurant, user)
    api_client.force_login(user)

    body = api_client.get(reverse("auth-me")).json()

    assert body["user"]["email"] == "alice@example.com"
    assert [m["restaurant"]["slug"] for m in body["memberships"]] == [restaurant.slug]


def test_logout_requires_csrf_then_ends_the_session(csrf_client, make_user):
    make_user(email="alice@example.com")
    csrf_client.get(reverse("auth-csrf"))
    post_login(csrf_client, "alice@example.com", **csrf_header(csrf_client))

    refused = csrf_client.post(reverse("auth-logout"))
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "csrf_failed"

    # Login rotates the CSRF token, so read the cookie again.
    assert csrf_client.post(reverse("auth-logout"), **csrf_header(csrf_client)).status_code == 204
    assert csrf_client.get(reverse("auth-me")).status_code == 401


def test_logout_requires_authentication(api_client):
    assert api_client.post(reverse("auth-logout")).status_code == 401
