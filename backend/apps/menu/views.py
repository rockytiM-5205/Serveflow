from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.common.exceptions import Conflict
from apps.common.schema import SLUG_PARAM, staff_schema
from apps.restaurants.models import MembershipRole, Restaurant
from apps.restaurants.permissions import RestaurantScopedMixin

from .models import MenuCategory, MenuItem
from .serializers import (
    AvailabilitySerializer,
    CategorySerializer,
    ItemSerializer,
    PublicMenuSerializer,
)

STAFF = MembershipRole.STAFF
MANAGER = MembershipRole.MANAGER
READ_BY_STAFF = {"GET": STAFF, "HEAD": STAFF, "OPTIONS": STAFF}

INCLUDE_ARCHIVED = OpenApiParameter("include_archived", bool, description="Set to 1 to include archived items")
CATEGORY_FILTER = OpenApiParameter("category", int, description="Only items in this category")


def save_or_conflict(serializer, **extra):
    """Save; a unique-name race that slips past validation becomes a clean 409."""
    try:
        with transaction.atomic():
            return serializer.save(**extra)
    except IntegrityError:
        raise Conflict("That name is already in use.", code="duplicate_name") from None


# ---------------------------------------------------------------- staff
@staff_schema(get="List categories", post="Create a category (manager or owner)")
class CategoryListCreateView(RestaurantScopedMixin, ListCreateAPIView):
    min_role = MANAGER
    min_roles = READ_BY_STAFF
    queryset = MenuCategory.objects.order_by("sort_order", "name", "id")
    serializer_class = CategorySerializer
    pagination_class = None  # menus are small; add pagination if one ever is not

    def perform_create(self, serializer):
        save_or_conflict(serializer, restaurant=self.request.restaurant)


@staff_schema(get="Get a category", patch="Update a category (manager or owner)")
class CategoryDetailView(RestaurantScopedMixin, RetrieveUpdateAPIView):
    min_role = MANAGER
    min_roles = READ_BY_STAFF
    queryset = MenuCategory.objects.all()
    serializer_class = CategorySerializer
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        save_or_conflict(serializer)


@staff_schema(
    extra_parameters=[INCLUDE_ARCHIVED, CATEGORY_FILTER],
    get="List items (archived hidden unless include_archived=1)",
    post="Create an item (manager or owner)",
)
class ItemListCreateView(RestaurantScopedMixin, ListCreateAPIView):
    min_role = MANAGER
    min_roles = READ_BY_STAFF
    queryset = MenuItem.objects.order_by("name", "id")
    serializer_class = ItemSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset
        params = self.request.query_params
        if params.get("include_archived") != "1":
            queryset = queryset.filter(archived_at__isnull=True)
        category = params.get("category", "")
        if category.isdigit():
            queryset = queryset.filter(category_id=int(category))
        return queryset

    def perform_create(self, serializer):
        save_or_conflict(serializer, restaurant=self.request.restaurant)


@staff_schema(get="Get an item", patch="Update an item; price changes are audited (manager or owner)")
class ItemDetailView(RestaurantScopedMixin, RetrieveUpdateAPIView):
    min_role = MANAGER
    min_roles = READ_BY_STAFF
    queryset = MenuItem.objects.all()
    serializer_class = ItemSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.is_archived:
            raise Conflict("Archived items cannot be edited.", code="item_archived")
        old_price = instance.price
        try:
            with transaction.atomic():
                item = serializer.save()
                if item.price != old_price:
                    record(
                        restaurant=self.request.restaurant,
                        actor=self.request.user,
                        action="menu_item.price_changed",
                        entity_type="menu_item",
                        entity_id=item.pk,
                        metadata={"item": item.name, "from": str(old_price), "to": str(item.price)},
                    )
        except IntegrityError:
            raise Conflict("That name is already in use.", code="duplicate_name") from None


class ItemArchiveView(RestaurantScopedMixin, GenericAPIView):
    min_role = MANAGER
    queryset = MenuItem.objects.all()
    serializer_class = ItemSerializer
    http_method_names = ["post", "options"]

    @extend_schema(
        parameters=[SLUG_PARAM], request=None, responses=ItemSerializer,
        summary="Archive an item (manager or owner). Safe to repeat.",
    )
    def post(self, request, *args, **kwargs):
        item = self.get_object()
        if not item.is_archived:
            with transaction.atomic():
                item.archive()
                record(
                    restaurant=request.restaurant,
                    actor=request.user,
                    action="menu_item.archived",
                    entity_type="menu_item",
                    entity_id=item.pk,
                    metadata={"item": item.name},
                )
        return Response(self.get_serializer(item).data)


class ItemAvailabilityView(RestaurantScopedMixin, GenericAPIView):
    min_role = STAFF
    queryset = MenuItem.objects.all()
    serializer_class = AvailabilitySerializer
    http_method_names = ["patch", "options"]

    @extend_schema(
        parameters=[SLUG_PARAM], request=AvailabilitySerializer, responses=ItemSerializer,
        summary="Mark an item available or unavailable (any staff role)",
    )
    def patch(self, request, *args, **kwargs):
        item = self.get_object()
        if item.is_archived:
            raise Conflict("Archived items cannot be changed.", code="item_archived")
        serializer = AvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.is_available = serializer.validated_data["is_available"]
        item.save(update_fields=["is_available", "updated_at"])
        return Response(ItemSerializer(item, context=self.get_serializer_context()).data)


# ---------------------------------------------------------------- public
class PublicMenuView(APIView):
    """What a customer sees: active categories that have visible items. No authentication."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(parameters=[SLUG_PARAM], responses=PublicMenuSerializer, summary="Public menu")
    def get(self, request, slug):
        restaurant = get_object_or_404(Restaurant.objects.filter(is_active=True), slug=slug)
        visible_items = MenuItem.objects.filter(archived_at__isnull=True).order_by("name", "id")
        categories = (
            MenuCategory.objects.filter(restaurant=restaurant, is_active=True)
            .order_by("sort_order", "name", "id")
            .prefetch_related(Prefetch("items", queryset=visible_items))
        )
        shown = [category for category in categories if category.items.all()]
        return Response(PublicMenuSerializer({"restaurant": restaurant, "categories": shown}).data)
