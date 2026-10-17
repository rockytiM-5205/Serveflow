"""Production. Refuses to start with unsafe configuration."""
from django.core.exceptions import ImproperlyConfigured

from config.env import env

from .base import *  # noqa: F401,F403

if DEBUG:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_DEBUG must not be enabled in production.")
if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list the production host names.")
if (
    SECRET_KEY.startswith(("change-me", "django-insecure-", "test-only"))  # noqa: F405
    or len(SECRET_KEY) < 50  # noqa: F405
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY looks like a placeholder or is too short; generate a real one (see .env.example)."
    )

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
X_FRAME_OPTIONS = "DENY"

# Start low and raise deliberately once HTTPS is confirmed; HSTS is hard to undo.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Only enable behind a trusted reverse proxy that sets and sanitises this header.
if env.bool("DJANGO_TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
