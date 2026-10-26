import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.menu.models import MenuItem
from apps.restaurants.models import MembershipRole, Restaurant, RestaurantMembership

pytestmark = pytest.mark.django_db


def test_seed_demo_creates_a_labelled_restaurant_owned_by_the_user(make_user):
    user = make_user(email="boss@example.com")
    call_command("seed_demo", owner_email="boss@example.com")
    restaurant = Restaurant.objects.get(slug="demo-kitchen")
    assert "sample" in restaurant.name.lower()
    assert restaurant.accepting_orders is True  # so the ordering flow can be tried
    assert RestaurantMembership.objects.get(restaurant=restaurant, user=user).role == MembershipRole.OWNER
    assert MenuItem.objects.filter(restaurant=restaurant, is_available=False).count() == 1


def test_seed_demo_is_repeatable(make_user):
    make_user(email="boss@example.com")
    call_command("seed_demo", owner_email="boss@example.com")
    first = MenuItem.objects.count()
    call_command("seed_demo", owner_email="boss@example.com")
    assert MenuItem.objects.count() == first
    assert Restaurant.objects.filter(slug="demo-kitchen").count() == 1


def test_seed_demo_needs_an_existing_user():
    with pytest.raises(CommandError):
        call_command("seed_demo", owner_email="nobody@example.com")


def test_seed_demo_refuses_to_run_with_production_settings(settings, make_user):
    make_user(email="boss@example.com")
    settings.SETTINGS_MODULE = "config.settings.production"
    with pytest.raises(CommandError):
        call_command("seed_demo", owner_email="boss@example.com")
    assert not Restaurant.objects.exists()
