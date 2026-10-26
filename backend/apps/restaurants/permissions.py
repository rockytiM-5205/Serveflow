"""Tenant access. Authorization comes from an active membership, never from User.is_staff."""
from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import BasePermission

from .models import MembershipRole, RestaurantMembership

ROLE_RANK = {
    MembershipRole.STAFF: 1,
    MembershipRole.MANAGER: 2,
    MembershipRole.OWNER: 3,
}


class HasRestaurantRole(BasePermission):
    """Requires an active membership in the restaurant named by the URL slug, with at
    least the view's ``min_role``. Re-read from the database on every request, so a
    deactivated membership or suspended restaurant loses access immediately. An unknown
    slug and a non-member get the same 403, so slugs cannot be probed through this.
    """

    def has_permission(self, request, view):
        get_min_role = getattr(view, "get_min_role", None)
        min_role = get_min_role(request) if get_min_role else getattr(view, "min_role", None)
        if min_role not in ROLE_RANK:
            # Fail closed: a staff view without an explicit role is a programming error.
            raise ImproperlyConfigured(f"{type(view).__name__} must set min_role to a MembershipRole.")

        user = request.user
        if not (user and user.is_authenticated):
            return False  # DRF turns this into 401 for anonymous callers

        membership = (
            RestaurantMembership.objects.select_related("restaurant")
            .filter(
                user=user,
                is_active=True,
                restaurant__is_active=True,
                restaurant__slug=view.kwargs.get("slug"),
            )
            .first()
        )
        if membership is None:
            self.code = "not_a_member"
            self.message = "You do not have access to this restaurant."
            return False
        if ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
            self.code = "insufficient_role"
            self.message = "Your role does not permit this action."
            return False

        request.membership = membership
        request.restaurant = membership.restaurant
        return True


class RestaurantScopedMixin:
    """Put first in the bases of every view mounted under /restaurants/<slug>/.

    Filters the queryset to the caller's restaurant, so an ID belonging to another
    restaurant is simply not found (404), on detail endpoints as well as lists.
    """

    permission_classes = [HasRestaurantRole]
    # min_role applies to every HTTP method not listed in min_roles. Set it to the strictest
    # role the view needs, then relax individual methods, e.g. min_roles = {"GET": STAFF}.
    min_role = None
    min_roles = {}
    restaurant_field = "restaurant"

    def get_min_role(self, request):
        return self.min_roles.get(request.method, self.min_role)

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):  # schema generation has no request.restaurant
            return queryset.none()
        return queryset.filter(**{self.restaurant_field: self.request.restaurant})


class CanCreateRestaurant(BasePermission):
    """Signed-in users who may create a restaurant (superusers, or self-service within the limit)."""

    def has_permission(self, request, view):
        from .services import can_create_restaurant  # local import: services imports this module

        user = request.user
        if not (user and user.is_authenticated):
            return False
        if can_create_restaurant(user):
            return True
        self.code = "restaurant_creation_unavailable"
        self.message = "This account can't create a restaurant."
        return False
