"""Configuration tests. None of these need a database connection."""
import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import require, settings_module


def test_database_is_postgresql_only(settings):
    engines = {db["ENGINE"] for db in settings.DATABASES.values()}
    assert engines == {"django.db.backends.postgresql"}


def test_custom_user_model_is_configured(settings):
    assert settings.AUTH_USER_MODEL == "accounts.User"


def test_debug_is_off(settings):
    assert settings.DEBUG is False


def test_timezone_support_enabled(settings):
    assert settings.USE_TZ is True


def test_api_denies_by_default(settings):
    perms = settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]
    assert perms == ["rest_framework.permissions.IsAuthenticated"]


def test_require_names_the_missing_variable(monkeypatch):
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    with pytest.raises(ImproperlyConfigured, match="POSTGRES_DB"):
        require("POSTGRES_DB")


def test_settings_module_defaults_to_production(monkeypatch):
    monkeypatch.delenv("DJANGO_ENV", raising=False)
    assert settings_module() == "config.settings.production"


def test_settings_module_rejects_unknown_environment(monkeypatch):
    monkeypatch.setenv("DJANGO_ENV", "staging")
    with pytest.raises(ImproperlyConfigured):
        settings_module()
