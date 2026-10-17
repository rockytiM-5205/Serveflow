"""Local development. Security relaxations here are limited to localhost use."""
from .base import *  # noqa: F401,F403

# DEBUG stays False unless DJANGO_DEBUG=True is set explicitly (see base.py).
if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
