"""Restaurants (tenants) and the memberships that grant staff access to them.

Authorization for restaurant operations comes only from an active
RestaurantMembership, never from User.is_staff / is_superuser.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models

from .validators import (
    CURRENCY_PATTERN,
    RESERVED_SLUGS,
    SLUG_PATTERN,
    validate_iana_timezone,
    validate_slug_not_reserved,
)


class MembershipRole(models.TextChoices):
    OWNER = "OWNER", "Owner"
    MANAGER = "MANAGER", "Manager"
    STAFF = "STAFF", "Staff"


class Restaurant(models.Model):
    name = models.CharField(max_length=120)
    slug = models.CharField(
        max_length=63,
        unique=True,
        validators=[
            MinLengthValidator(3),
            RegexValidator(SLUG_PATTERN, "Use lowercase letters, digits and single hyphens."),
            validate_slug_not_reserved,
        ],
        help_text="Public URL identifier. Lowercase letters, digits and hyphens.",
    )
    description = models.TextField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=255, blank=True)

    # is_active: platform-level switch (suspended restaurants are not public).
    # accepting_orders: operational switch staff can flip to pause new orders.
    is_active = models.BooleanField(default=True)
    accepting_orders = models.BooleanField(
        default=False,
        help_text="New restaurants do not take orders until this is switched on.",
    )

    # No defaults: these are per-restaurant facts and must be set deliberately.
    currency = models.CharField(
        max_length=3,
        validators=[RegexValidator(CURRENCY_PATTERN, "Use a 3-letter uppercase code, e.g. USD.")],
        help_text="ISO 4217 code. Format is validated; the code list is not.",
    )
    timezone = models.CharField(max_length=64, validators=[validate_iana_timezone])

    # Fulfilment options a customer may choose per order.
    pickup_enabled = models.BooleanField(default=True)
    dine_in_enabled = models.BooleanField(default=False)
    requires_table_number = models.BooleanField(
        default=False,
        help_text="Dine-in orders must include a table number. Requires dine-in.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pickup_enabled=True) | models.Q(dine_in_enabled=True),
                name="restaurants_restaurant_fulfilment_enabled",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_table_number=False) | models.Q(dine_in_enabled=True),
                name="restaurants_restaurant_table_requires_dine_in",
            ),
            models.CheckConstraint(
                condition=models.Q(slug__regex=SLUG_PATTERN),
                name="restaurants_restaurant_slug_format",
            ),
            models.CheckConstraint(
                condition=~models.Q(slug__in=RESERVED_SLUGS),
                name="restaurants_restaurant_slug_not_reserved",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=CURRENCY_PATTERN),
                name="restaurants_restaurant_currency_format",
            ),
        ]

    def __str__(self):
        return self.name


class RestaurantMembership(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="memberships"
    )
    # PROTECT: accounts are deactivated, not deleted, so history stays intact.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="restaurant_memberships",
    )
    role = models.CharField(
        max_length=16, choices=MembershipRole.choices, default=MembershipRole.STAFF
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "user"],
                name="restaurants_membership_unique_user_per_restaurant",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=MembershipRole.values),
                name="restaurants_membership_role_valid",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.restaurant} ({self.role})"

    def clean(self):
        super().clean()
        # Last-owner rule. This validation covers forms and admin only; it is not
        # race-safe and is bypassed by queryset.update(). The member-management
        # service (later stage) must enforce it again under a row lock.
        if not self.pk or not self.restaurant_id:
            return
        previous = (
            RestaurantMembership.objects.filter(pk=self.pk).values("role", "is_active").first()
        )
        if not previous or previous["role"] != MembershipRole.OWNER or not previous["is_active"]:
            return
        if self.role == MembershipRole.OWNER and self.is_active:
            return
        other_active_owner = (
            RestaurantMembership.objects.filter(
                restaurant_id=self.restaurant_id,
                role=MembershipRole.OWNER,
                is_active=True,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if not other_active_owner:
            raise ValidationError("A restaurant must keep at least one active owner.")
