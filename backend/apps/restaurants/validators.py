"""Shared constants and validators for restaurant configuration."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"

# Slugs that would collide with platform URLs. Enforced here (friendly form errors)
# and by a database CHECK constraint. Changing this tuple requires a migration.
RESERVED_SLUGS = (
    "admin",
    "api",
    "app",
    "auth",
    "docs",
    "health",
    "login",
    "logout",
    "media",
    "menu",
    "order",
    "orders",
    "restaurant",
    "restaurants",
    "schema",
    "settings",
    "static",
    "status",
    "www",
)


def validate_slug_not_reserved(value):
    if value in RESERVED_SLUGS:
        raise ValidationError("This slug is reserved by the platform.", code="reserved_slug")


def validate_iana_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValidationError(
            "Enter a valid IANA timezone name, for example 'Europe/London'.",
            code="invalid_timezone",
        )
