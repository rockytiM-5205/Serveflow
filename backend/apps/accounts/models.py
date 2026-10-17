# The custom email-login User model is implemented in the next stage.
# AUTH_USER_MODEL = "accounts.User" is already configured; do not run
# `migrate` until accounts/migrations/0001_initial.py exists and is reviewed.

from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    pass