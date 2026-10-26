"""Restaurant and membership model tests. Need PostgreSQL and both migrations."""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.restaurants.models import MembershipRole, Restaurant, RestaurantMembership

pytestmark = pytest.mark.django_db


# --- Restaurant ---------------------------------------------------------------


def test_new_restaurant_defaults(make_restaurant):
    r = make_restaurant()
    assert r.is_active is True
    assert r.accepting_orders is False  # must be switched on deliberately
    assert r.pickup_enabled is True
    assert r.dine_in_enabled is False
    assert r.requires_table_number is False


def test_slug_is_unique(make_restaurant):
    make_restaurant(slug="green-bowl")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_restaurant(slug="green-bowl")


@pytest.mark.parametrize("slug", ["Upper", "has_underscore", "-lead", "trail-", "dou--ble", "sp ace"])
def test_database_rejects_malformed_slug(make_restaurant, slug):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_restaurant(slug=slug)


@pytest.mark.parametrize("slug", ["admin", "api", "static"])
def test_database_rejects_reserved_slug(make_restaurant, slug):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_restaurant(slug=slug)


def test_full_clean_reports_reserved_slug():
    r = Restaurant(name="X", slug="admin", currency="USD", timezone="UTC")
    with pytest.raises(ValidationError) as exc:
        r.full_clean()
    assert "slug" in exc.value.message_dict


@pytest.mark.parametrize("currency", ["usd", "US", "USDD", "12A"])
def test_database_rejects_malformed_currency(make_restaurant, currency):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_restaurant(currency=currency)


def test_full_clean_rejects_unknown_timezone():
    r = Restaurant(name="X", slug="valid-slug", currency="USD", timezone="Mars/Olympus")
    with pytest.raises(ValidationError) as exc:
        r.full_clean()
    assert "timezone" in exc.value.message_dict


def test_full_clean_accepts_real_timezone():
    Restaurant(
        name="X", slug="valid-slug", currency="USD", timezone="Europe/London"
    ).full_clean()


def test_at_least_one_fulfilment_type_must_be_enabled(make_restaurant):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_restaurant(pickup_enabled=False, dine_in_enabled=False)


def test_dine_in_only_is_allowed(make_restaurant):
    make_restaurant(pickup_enabled=False, dine_in_enabled=True)


def test_table_number_requirement_needs_dine_in(make_restaurant):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_restaurant(dine_in_enabled=False, requires_table_number=True)
    make_restaurant(dine_in_enabled=True, requires_table_number=True)


# --- Membership ---------------------------------------------------------------


def test_membership_defaults_to_least_privilege(make_restaurant, make_user):
    m = RestaurantMembership.objects.create(restaurant=make_restaurant(), user=make_user())
    assert m.role == MembershipRole.STAFF
    assert m.is_active is True


def test_user_can_belong_to_two_restaurants(make_restaurant, make_user):
    user = make_user()
    RestaurantMembership.objects.create(restaurant=make_restaurant(), user=user)
    RestaurantMembership.objects.create(restaurant=make_restaurant(), user=user)
    assert user.restaurant_memberships.count() == 2


def test_one_membership_per_user_per_restaurant(make_restaurant, make_user):
    restaurant, user = make_restaurant(), make_user()
    RestaurantMembership.objects.create(restaurant=restaurant, user=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        RestaurantMembership.objects.create(restaurant=restaurant, user=user)


def test_database_rejects_unknown_role(make_restaurant, make_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        RestaurantMembership.objects.create(
            restaurant=make_restaurant(), user=make_user(), role="BOSS"
        )


def test_last_active_owner_cannot_be_demoted_or_deactivated(make_restaurant, make_user):
    restaurant = make_restaurant()
    owner = RestaurantMembership.objects.create(
        restaurant=restaurant, user=make_user(), role=MembershipRole.OWNER
    )
    owner.role = MembershipRole.MANAGER
    with pytest.raises(ValidationError):
        owner.full_clean()

    owner.role = MembershipRole.OWNER
    owner.is_active = False
    with pytest.raises(ValidationError):
        owner.full_clean()


def test_owner_can_be_demoted_when_another_active_owner_exists(make_restaurant, make_user):
    restaurant = make_restaurant()
    first = RestaurantMembership.objects.create(
        restaurant=restaurant, user=make_user(), role=MembershipRole.OWNER
    )
    RestaurantMembership.objects.create(
        restaurant=restaurant, user=make_user(), role=MembershipRole.OWNER
    )
    first.role = MembershipRole.MANAGER
    first.full_clean()
    first.save()


def test_users_with_memberships_cannot_be_deleted(make_restaurant, make_user):
    user = make_user()
    RestaurantMembership.objects.create(restaurant=make_restaurant(), user=user)
    with pytest.raises(ProtectedError):
        user.delete()


def test_deleting_a_restaurant_removes_its_memberships(make_restaurant, make_user):
    restaurant = make_restaurant()
    RestaurantMembership.objects.create(restaurant=restaurant, user=make_user())
    restaurant.delete()
    assert RestaurantMembership.objects.count() == 0
