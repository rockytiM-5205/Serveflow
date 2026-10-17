"""Environment loading shared by manage.py, wsgi.py, asgi.py and the settings.

Loads the repository-root ``.env`` file when it exists. Real environment
variables always win over values in the file. ``require`` fails loudly with an
actionable message instead of silently falling back to a default.
"""
import os
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALID_ENVIRONMENTS = ("development", "testing", "production")

env = environ.Env()

_ENV_FILE = REPO_ROOT / ".env"
if _ENV_FILE.is_file():
    environ.Env.read_env(str(_ENV_FILE))


def require(name: str, hint: str = "") -> str:
    """Return a mandatory environment variable or raise a clear error."""
    value = os.environ.get(name, "").strip()
    if not value:
        message = (
            f"Missing required environment variable {name}. "
            "Copy .env.example to .env in the repository root and set it "
            "(see README.md)."
        )
        raise ImproperlyConfigured(f"{message} {hint}".strip())
    return value


def settings_module() -> str:
    """Map DJANGO_ENV to a settings module. Defaults to production (strictest)."""
    name = os.environ.get("DJANGO_ENV", "production").strip().lower()
    if name not in VALID_ENVIRONMENTS:
        raise ImproperlyConfigured(
            f"DJANGO_ENV must be one of {', '.join(VALID_ENVIRONMENTS)}; got {name!r}."
        )
    return f"config.settings.{name}"
