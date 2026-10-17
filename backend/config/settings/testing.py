"""Automated tests. Still PostgreSQL: the test database is created by pytest-django."""
import os

# Test-only value; it protects nothing and must never be used elsewhere.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-used-outside-automated-tests")

from .base import *  # noqa: E402,F401,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only
