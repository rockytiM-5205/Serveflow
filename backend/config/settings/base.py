"""Settings shared by every environment. Environment-specific modules extend this."""
from pathlib import Path

from config.env import env, require

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

_DB_HINT = "ServeFlow requires PostgreSQL; there is no SQLite fallback."

# --- Core security -----------------------------------------------------------
SECRET_KEY = require("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
# Platform admin lives at a configurable path; set a non-default value in production.
ADMIN_URL = env.str("DJANGO_ADMIN_URL", default="admin/").strip("/") + "/"

# --- Self-service onboarding --------------------------------------------------
# When on, anyone can create an account and a restaurant from the dashboard (no Django admin
# needed). Off by default: turn it on deliberately, because public sign-up invites spam.
SELF_SERVICE = env.bool("DJANGO_SELF_SERVICE", default=False)
MAX_RESTAURANTS_PER_USER = 5

# --- Applications ------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "drf_spectacular",
    # ServeFlow
    "apps.accounts",
    "apps.restaurants",
    "apps.menu",
    "apps.audit",
    "apps.orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database: PostgreSQL only -----------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": require("POSTGRES_DB", _DB_HINT),
        "USER": require("POSTGRES_USER", _DB_HINT),
        "PASSWORD": require("POSTGRES_PASSWORD", _DB_HINT),
        # "HOST": require("POSTGRES_HOST", _DB_HINT),
        # "PORT": require("POSTGRES_PORT", _DB_HINT),
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication ----------------------------------------------------------
# The custom email-login User is implemented in the next stage. It must exist
# (with its first migration) before any other app migrates.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation and time ------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # Stored times are UTC; restaurants carry their own timezone.
USE_I18N = True
USE_TZ = True

# --- Static files ------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Django REST Framework ---------------------------------------------------
# Deny by default: public endpoints must opt in with AllowAny and
# authentication_classes = [] explicitly.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.common.authentication.CsrfSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login_ip": "5/min",
        "login_email": "5/min",
        "signup": "10/hour",
        "restaurant_create": "10/hour",
        "password_change": "5/min",
        "order_create": "30/min",
        "order_phone": "20/hour",
        "order_lookup": "600/min",
        "order_cancel": "10/min",
    },
}

# Throttle counters live in the cache. LocMemCache is per process: with several
# workers each keeps its own count, so limits are weaker than they look. Use a shared
# cache (Redis, or Django's database cache) before running more than one worker.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SPECTACULAR_SETTINGS = {
    "TITLE": "ServeFlow API",
    "DESCRIPTION": "Multi-tenant restaurant ordering API.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
}

# Print server errors (with tracebacks) to the terminal even when DEBUG is off.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
