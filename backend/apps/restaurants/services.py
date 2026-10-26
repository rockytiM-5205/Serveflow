"""Business rules for restaurants and their members. Views stay thin and call these."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record
from apps.common.exceptions import Conflict

from .models import MembershipRole, Restaurant, RestaurantMembership
from .permissions import ROLE_RANK

OWNER, MANAGER, STAFF = MembershipRole.OWNER, MembershipRole.MANAGER, MembershipRole.STAFF


def can_create_restaurant(user):
    if user.is_superuser:
        return True
    if not settings.SELF_SERVICE:
        return False
    owned = RestaurantMembership.objects.filter(user=user, role=OWNER, is_active=True).count()
    return owned < settings.MAX_RESTAURANTS_PER_USER


@transaction.atomic
def create_restaurant(user, data):
    restaurant = Restaurant.objects.create(**data)
    RestaurantMembership.objects.create(restaurant=restaurant, user=user, role=OWNER)
    return restaurant


def check_password_strength(password, user=None, field="password"):
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({field: list(exc.messages)}) from None


def _fresh_actor(restaurant, actor):
    """Re-read the caller's membership under lock: it may have changed since the request began."""
    Restaurant.objects.select_for_update().get(pk=restaurant.pk)  # serialise membership changes per restaurant
    actor = RestaurantMembership.objects.select_for_update().get(pk=actor.pk)
    if not actor.is_active or ROLE_RANK[actor.role] < ROLE_RANK[MANAGER]:
        raise PermissionDenied("Your role no longer permits this action.", code="insufficient_role")
    return actor


def add_member(*, restaurant, actor, email, role, password="", first_name="", last_name=""):
    """Add a person to the restaurant. `actor` is the caller's own membership.

    Managers may add staff; only owners may add managers or owners. An existing account is
    attached as is; otherwise a new account is created with the given starting password.
    """
    User = get_user_model()
    email = email.strip().lower()
    with transaction.atomic():
        actor = _fresh_actor(restaurant, actor)
        if role != STAFF and actor.role != OWNER:
            raise PermissionDenied("Only owners can add managers or owners.", code="insufficient_role")
        user = User.objects.filter(email=email).first()
        if user is None:
            if not password:
                raise ValidationError({"password": ["Set a starting password for the new account."]})
            check_password_strength(password, User(email=email, first_name=first_name, last_name=last_name))
            user = User.objects.create_user(email, password, first_name=first_name, last_name=last_name)
        elif RestaurantMembership.objects.filter(restaurant=restaurant, user=user).exists():
            raise Conflict("This person is already a member.", code="already_member")
        membership = RestaurantMembership.objects.create(restaurant=restaurant, user=user, role=role)
        record(
            restaurant=restaurant, actor=actor.user, action="membership.added",
            entity_type="membership", entity_id=membership.pk, metadata={"role": role},
        )
    return membership


def change_member(*, restaurant, actor, target, role=None, is_active=None):
    """Change a member's role or active flag. Safe against two people removing the last owner."""
    with transaction.atomic():
        actor = _fresh_actor(restaurant, actor)
        target = RestaurantMembership.objects.select_for_update().get(pk=target.pk)

        if target.pk == actor.pk:
            raise PermissionDenied("You can't change your own membership.", code="cannot_modify_self")
        if ROLE_RANK[actor.role] < ROLE_RANK[OWNER] and (target.role != STAFF or role not in (None, STAFF)):
            raise PermissionDenied("Only owners can change managers and owners.", code="insufficient_role")

        new_role = target.role if role is None else role
        new_active = target.is_active if is_active is None else is_active
        loses_an_owner = target.role == OWNER and target.is_active and not (new_role == OWNER and new_active)
        if loses_an_owner and not (
            RestaurantMembership.objects.filter(restaurant=restaurant, role=OWNER, is_active=True)
            .exclude(pk=target.pk)
            .exists()
        ):
            raise Conflict("A restaurant must keep at least one active owner.", code="last_owner")

        before = {"role": target.role, "is_active": target.is_active}
        target.role, target.is_active = new_role, new_active
        target.save(update_fields=["role", "is_active"])
        if before != {"role": target.role, "is_active": target.is_active}:
            record(
                restaurant=restaurant, actor=actor.user, action="membership.changed",
                entity_type="membership", entity_id=target.pk,
                metadata={"from": before, "to": {"role": target.role, "is_active": target.is_active}},
            )
    return target
