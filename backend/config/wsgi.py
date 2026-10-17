"""WSGI entry point."""
import os

from django.core.wsgi import get_wsgi_application

from config.env import settings_module

os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module())
application = get_wsgi_application()
