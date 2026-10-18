"""User model tests. These need PostgreSQL and the accounts migration."""
import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_custom_user_model_is_active():
    assert User._meta.label == "accounts.User"
    assert User.USERNAME_FIELD == "email"


def test_create_user_normalizes_email_and_hashes_password():
    user = User.objects.create_user("  Alice@Example.COM ", "s3cret-pass-123")
    assert user.email == "alice@example.com"
    assert user.password != "s3cret-pass-123"
    assert user.check_password("s3cret-pass-123")


def test_create_user_defaults_to_no_admin_access():
    user = User.objects.create_user("a@example.com", "pw")
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False


def test_create_user_without_password_has_unusable_password():
    user = User.objects.create_user("a@example.com")
    assert not user.has_usable_password()


@pytest.mark.parametrize("email", ["", "   ", None])
def test_create_user_requires_email(email):
    with pytest.raises(ValueError):
        User.objects.create_user(email, "pw")


def test_create_superuser_sets_admin_flags():
    admin = User.objects.create_superuser("root@example.com", "pw")
    assert admin.is_staff and admin.is_superuser


def test_create_superuser_rejects_contradictory_flags():
    with pytest.raises(ValueError):
        User.objects.create_superuser("root@example.com", "pw", is_staff=False)
    with pytest.raises(ValueError):
        User.objects.create_superuser("root@example.com", "pw", is_superuser=False)


def test_emails_differing_only_by_case_collide():
    User.objects.create_user("a@example.com", "pw")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("A@Example.com", "pw")


def test_database_rejects_mixed_case_email_even_if_save_is_bypassed():
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="Mixed@Example.com")])


def test_authenticate_ignores_email_case():
    User.objects.create_user("alice@example.com", "s3cret-pass-123")
    assert authenticate(email="ALICE@example.com", password="s3cret-pass-123") is not None
    assert authenticate(email="alice@example.com", password="wrong") is None


def test_inactive_user_cannot_authenticate():
    User.objects.create_user("gone@example.com", "s3cret-pass-123", is_active=False)
    assert authenticate(email="gone@example.com", password="s3cret-pass-123") is None


def test_string_and_name_helpers():
    user = User.objects.create_user("a@example.com", "pw", first_name="Ada", last_name="Obi")
    assert str(user) == "a@example.com"
    assert user.get_full_name() == "Ada Obi"
    assert user.get_short_name() == "Ada"
