"""Development helper: one clearly labelled demo restaurant with sample menu items.

Refuses to run outside development/testing settings, so sample data can never reach
production. Safe to run repeatedly.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.menu.models import MenuCategory, MenuItem
from apps.restaurants.models import MembershipRole, Restaurant, RestaurantMembership

SLUG = "demo-kitchen"
SAMPLE = {
    "Sample mains": [
        ("Sample rice, per spoon", "0.50", "spoon", True),
        ("Sample rice, full plate", "3.00", "plate", True),
        ("Sample beans", "1.00", "portion", True),
    ],
    "Sample sides": [("Sample chicken", "2.50", "piece", True)],
    "Sample drinks": [("Sample water", "0.75", "bottle", False)],
}


class Command(BaseCommand):
    help = "Create a demo restaurant with sample data and make an existing user its owner (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--owner-email", required=True, help="Email of an existing user (e.g. your superuser).")

    @transaction.atomic
    def handle(self, *args, owner_email, **options):
        if not settings.SETTINGS_MODULE.endswith((".development", ".testing")):
            raise CommandError("seed_demo only runs with development settings (DJANGO_ENV=development).")
        try:
            owner = get_user_model().objects.get(email=owner_email.strip().lower())
        except get_user_model().DoesNotExist:
            raise CommandError(f"No user with email {owner_email!r}. Create one with createsuperuser first.") from None

        restaurant, _ = Restaurant.objects.get_or_create(
            slug=SLUG,
            defaults={
                "name": "Demo Kitchen (sample data)",
                "description": "Sample data for development. This is not a real restaurant.",
                "currency": "USD",
                "timezone": "UTC",
                "dine_in_enabled": True,
                "accepting_orders": True,
            },
        )
        RestaurantMembership.objects.get_or_create(
            restaurant=restaurant, user=owner, defaults={"role": MembershipRole.OWNER}
        )
        for order, (category_name, items) in enumerate(SAMPLE.items()):
            category, _ = MenuCategory.objects.get_or_create(
                restaurant=restaurant, name=category_name, defaults={"sort_order": order}
            )
            for name, price, unit, available in items:
                MenuItem.objects.get_or_create(
                    restaurant=restaurant, name=name,
                    defaults={"category": category, "price": Decimal(price), "unit_name": unit, "is_available": available},
                )
        self.stdout.write(self.style.SUCCESS(f"Demo restaurant ready: slug '{SLUG}', owner {owner.email}."))
        self.stdout.write(f"Customer page: http://localhost:5173/customer/index.html?r={SLUG}")
        self.stdout.write("Staff dashboard: http://localhost:5173/restaurant-dashboard/login.html")
