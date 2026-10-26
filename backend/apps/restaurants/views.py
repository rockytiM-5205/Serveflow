from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import (
    CreateAPIView, GenericAPIView, ListCreateAPIView, RetrieveAPIView, RetrieveUpdateAPIView,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.audit.services import record
from apps.common.pagination import DefaultCursorPagination
from apps.common.schema import SLUG_PARAM, staff_schema

from .models import MembershipRole, Restaurant, RestaurantMembership
from .permissions import ROLE_RANK, CanCreateRestaurant, RestaurantScopedMixin
from .serializers import (
    MemberCreateSerializer, MemberSerializer, MemberUpdateSerializer, PublicRestaurantSerializer,
    RestaurantSettingsSerializer, RestaurantWriteSerializer,
)
from .services import add_member, change_member, create_restaurant


class MembersPagination(DefaultCursorPagination):
    ordering = ("created_at", "id")


@staff_schema(get="List the restaurant's members (manager or owner)")
class MemberListView(RestaurantScopedMixin, ListCreateAPIView):
    min_role = MembershipRole.MANAGER
    queryset = RestaurantMembership.objects.select_related("user")
    serializer_class = MemberSerializer
    pagination_class = MembersPagination

    @extend_schema(
        parameters=[SLUG_PARAM], request=MemberCreateSerializer, responses={201: MemberSerializer},
        summary="Add a member. Managers add staff; owners add any role.",
    )
    def post(self, request, *args, **kwargs):
        serializer = MemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = add_member(restaurant=request.restaurant, actor=request.membership, **serializer.validated_data)
        return Response(MemberSerializer(membership).data, status=201)


class MemberDetailView(RestaurantScopedMixin, GenericAPIView):
    min_role = MembershipRole.MANAGER
    queryset = RestaurantMembership.objects.select_related("user")
    serializer_class = MemberUpdateSerializer
    http_method_names = ["patch", "options"]

    @extend_schema(
        parameters=[SLUG_PARAM], request=MemberUpdateSerializer, responses=MemberSerializer,
        summary="Change a member's role or deactivate/reactivate them",
    )
    def patch(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = MemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = change_member(
            restaurant=request.restaurant, actor=request.membership, target=target, **serializer.validated_data
        )
        return Response(MemberSerializer(updated).data)


@staff_schema(
    get="Restaurant settings",
    patch="Update settings. Staff may only change accepting_orders; managers and owners may change all.",
)
class RestaurantSettingsView(RestaurantScopedMixin, RetrieveUpdateAPIView):
    min_role = MembershipRole.STAFF
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSettingsSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Restaurant.objects.none()
        return Restaurant.objects.filter(pk=self.request.restaurant.pk)

    def get_object(self):
        restaurant = self.get_queryset().get()
        self.check_object_permissions(self.request, restaurant)
        return restaurant

    def perform_update(self, serializer):
        if ROLE_RANK[self.request.membership.role] < ROLE_RANK[MembershipRole.MANAGER]:
            if set(self.request.data) - {"accepting_orders"}:
                raise PermissionDenied("Only managers and owners can change these settings.", code="insufficient_role")
        before = {name: getattr(serializer.instance, name) for name in serializer.validated_data}
        with transaction.atomic():
            restaurant = serializer.save()
            changed = sorted(name for name, old in before.items() if getattr(restaurant, name) != old)
            if changed:
                record(
                    restaurant=restaurant, actor=self.request.user, action="restaurant.settings_changed",
                    entity_type="restaurant", entity_id=restaurant.pk, metadata={"changed": changed},
                )


class RestaurantCreateView(CreateAPIView):
    """Any signed-in user who is allowed to (see can_create_restaurant) can open a restaurant."""

    permission_classes = [CanCreateRestaurant]
    serializer_class = RestaurantWriteSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "restaurant_create"

    @extend_schema(
        request=RestaurantWriteSerializer, responses={201: PublicRestaurantSerializer},
        summary="Create a restaurant; the caller becomes its owner",
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            restaurant = create_restaurant(request.user, serializer.validated_data)
        except IntegrityError:
            raise ValidationError({"slug": ["This address is already taken."]}) from None
        return Response(PublicRestaurantSerializer(restaurant).data, status=201)


class PublicRestaurantView(RetrieveAPIView):
    """Public restaurant details by slug. Suspended restaurants look like they do not exist."""

    authentication_classes = []
    permission_classes = [AllowAny]
    queryset = Restaurant.objects.filter(is_active=True)
    serializer_class = PublicRestaurantSerializer
    lookup_field = "slug"
