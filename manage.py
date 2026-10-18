#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Is it installed and is your virtual "
            "environment activated? See README.md."
        ) from exc

    from config.env import settings_module

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module())
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
