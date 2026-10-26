"""Adding and changing members. Need PostgreSQL and the migrations."""
import pytest
from django.contrib.auth import authenticate, get_user_model
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied

from apps.audit.models import AuditLog
from apps.restaurants.models import MembershipRole, RestaurantMembership
from apps.restaurants.services import change_member

pytestmark = pytest.mark.django_db

STAFF, MANAGER, OWNER = MembershipRole.STAFF, MembershipRole.MANAGER, MembershipRole.OWNER
NEW_PASSWORD = "a-long-unusual-pass-9"


def list_url(restaurant):
    return reverse("restaurant-members", kwargs={"slug": restaurant.slug})


def detail_url(restaurant, membership):
    return reverse("restaurant-member", kwargs={"slug": restaurant.slug, "pk": membership.pk})


def add(client, restaurant, **body):
    return client.post(list_url(restaurant), {"email": "Cook@Example.com", "password": NEW_PASSWORD, **body}, format="json")


def code(response):
    return response.json()["error"]["code"]


# ---------------------------------------------------------------- adding
def test_manager_adds_a_staff_member_with_a_new_account(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, MANAGER)

    response = add(api_client, restaurant, first_name="Sam")

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "STAFF" and body["user"]["email"] == "cook@example.com"
    assert "password" not in response.content.decode()
    assert authenticate(email="cook@example.com", password=NEW_PASSWORD) is not None
    assert AuditLog.objects.filter(action="membership.added").count() == 1


def test_a_new_account_needs_a_strong_starting_password(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, MANAGER)
    assert "password" in add(api_client, restaurant, password="").json()["error"]["details"]
    assert "password" in add(api_client, restaurant, password="12345678").json()["error"]["details"]
    assert not get_user_model().objects.filter(email="cook@example.com").exists()


def test_existing_accounts_are_attached_without_a_password(api_client, make_restaurant, make_user, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, MANAGER)
    existing = make_user(email="cook@example.com")
    response = add(api_client, restaurant, password="")
    assert response.status_code == 201 and response.json()["user"]["id"] == existing.pk
    again = add(api_client, restaurant, password="")
    assert again.status_code == 409 and code(again) == "already_member"


def test_only_owners_can_add_managers_and_owners(api_client, make_restaurant, make_membership, make_user, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, MANAGER)
    refused = add(api_client, restaurant, role="MANAGER")
    assert refused.status_code == 403 and code(refused) == "insufficient_role"

    api_client.logout()
    owner = make_user()
    make_membership(restaurant, owner, OWNER)
    api_client.force_login(owner)
    assert add(api_client, restaurant, role="MANAGER").status_code == 201


def test_staff_cannot_add_members(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, STAFF)
    assert add(api_client, restaurant).status_code == 403


def test_invalid_role_is_rejected(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, OWNER)
    assert add(api_client, restaurant, role="BOSS").status_code == 400


# ---------------------------------------------------------------- changing
@pytest.fixture
def team(make_restaurant, make_user, make_membership):
    """A restaurant with an owner, a manager and a staff member."""
    restaurant = make_restaurant()
    people = {role: make_user() for role in (OWNER, MANAGER, STAFF)}
    memberships = {role: make_membership(restaurant, user, role) for role, user in people.items()}
    return restaurant, people, memberships


def test_manager_can_deactivate_and_reactivate_staff(api_client, team):
    restaurant, people, memberships = team
    api_client.force_login(people[MANAGER])
    off = api_client.patch(detail_url(restaurant, memberships[STAFF]), {"is_active": False}, format="json")
    assert off.status_code == 200 and off.json()["is_active"] is False
    on = api_client.patch(detail_url(restaurant, memberships[STAFF]), {"is_active": True}, format="json")
    assert on.json()["is_active"] is True
    assert AuditLog.objects.filter(action="membership.changed").count() == 2


def test_deactivated_staff_lose_access_immediately(api_client, team):
    restaurant, people, memberships = team
    memberships[STAFF].is_active = False
    memberships[STAFF].save()
    api_client.force_login(people[STAFF])
    me = api_client.get(reverse("auth-me")).json()
    assert me["memberships"] == []


def test_managers_cannot_touch_managers_owners_or_promote(api_client, team, make_membership, make_user):
    restaurant, people, memberships = team
    api_client.force_login(people[MANAGER])
    other_manager = make_membership(restaurant, make_user(), MANAGER)
    for target in (memberships[OWNER], other_manager):
        response = api_client.patch(detail_url(restaurant, target), {"is_active": False}, format="json")
        assert response.status_code == 403 and code(response) == "insufficient_role"
    promote = api_client.patch(detail_url(restaurant, memberships[STAFF]), {"role": "MANAGER"}, format="json")
    assert promote.status_code == 403
    memberships[STAFF].refresh_from_db()
    assert memberships[STAFF].role == STAFF


def test_owner_can_promote_and_demote(api_client, team):
    restaurant, people, memberships = team
    api_client.force_login(people[OWNER])
    assert api_client.patch(detail_url(restaurant, memberships[STAFF]), {"role": "MANAGER"}, format="json").json()["role"] == "MANAGER"
    assert api_client.patch(detail_url(restaurant, memberships[MANAGER]), {"role": "STAFF"}, format="json").json()["role"] == "STAFF"


def test_nobody_can_change_their_own_membership(api_client, team):
    restaurant, people, memberships = team
    api_client.force_login(people[OWNER])
    response = api_client.patch(detail_url(restaurant, memberships[OWNER]), {"role": "STAFF"}, format="json")
    assert response.status_code == 403 and code(response) == "cannot_modify_self"


def test_staff_cannot_change_members(api_client, team):
    restaurant, people, memberships = team
    api_client.force_login(people[STAFF])
    assert api_client.patch(detail_url(restaurant, memberships[STAFF]), {"is_active": False}, format="json").status_code == 403


def test_another_restaurants_membership_is_404(api_client, team, make_restaurant, make_user, make_membership):
    restaurant, people, _ = team
    foreign = make_membership(make_restaurant(), make_user(), STAFF)
    api_client.force_login(people[OWNER])
    assert api_client.patch(detail_url(restaurant, foreign), {"is_active": False}, format="json").status_code == 404


def test_an_empty_change_is_rejected(api_client, team):
    restaurant, people, memberships = team
    api_client.force_login(people[OWNER])
    assert api_client.patch(detail_url(restaurant, memberships[STAFF]), {}, format="json").status_code == 400


def test_a_stale_caller_cannot_act_after_being_demoted(make_restaurant, make_user, make_membership):
    """Two owners act at once: the one demoted first must not then remove the other."""
    restaurant = make_restaurant()
    a = make_membership(restaurant, make_user(), OWNER)
    b = make_membership(restaurant, make_user(), OWNER)
    stale_b = RestaurantMembership.objects.get(pk=b.pk)  # still looks like an owner

    change_member(restaurant=restaurant, actor=a, target=b, role=MANAGER)  # A demotes B first

    with pytest.raises(PermissionDenied):
        change_member(restaurant=restaurant, actor=stale_b, target=a, is_active=False)
    a.refresh_from_db()
    assert a.is_active and a.role == OWNER
