"""Customer-facing order endpoints. No cookies and no sign-in: the order token is the credential."""
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.schema import SLUG_PARAM
from apps.restaurants.models import Restaurant

from . import idempotency
from .models import ActorType, IdempotencyScope, Order, OrderStatus
from .serializers import OrderCreatedSerializer, OrderCreateSerializer, PublicOrderSerializer
from .services import create_order
from .throttles import OrderPhoneThrottle
from .tokens import make_token, parse_token, verify_token
from .workflow import change_status

# Order links are bearer secrets: never cache them, never leak them in referrers.
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
IDEMPOTENCY_PARAM = OpenApiParameter(
    "Idempotency-Key", str, location=OpenApiParameter.HEADER, required=True,
    description="A unique value (16-64 letters, digits, - or _) generated once per order attempt. Retrying with the same key never creates a second order.",
)
TOKEN_PARAM = OpenApiParameter("token", str, location=OpenApiParameter.PATH, description="The order link token")


def load_order(token):
    """The order for a valid token. Malformed, unknown, forged and revoked tokens all look the same."""
    public_id = parse_token(token)
    order = None
    if public_id is not None:
        order = (
            Order.objects.select_related("restaurant")
            .prefetch_related("items", "events")
            .filter(public_id=public_id)
            .first()
        )
    if order is None or not verify_token(token, order):
        raise NotFound("We can't find that order.")
    return order


class OrderCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle, OrderPhoneThrottle]
    throttle_scope = "order_create"

    @extend_schema(
        parameters=[SLUG_PARAM, IDEMPOTENCY_PARAM], request=OrderCreateSerializer, responses={201: OrderCreatedSerializer},
        summary="Place an order as a guest. Prices are calculated by the server.",
    )
    def post(self, request, slug):
        restaurant = get_object_or_404(Restaurant.objects.filter(is_active=True), slug=slug)
        key = idempotency.read_key(request)
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_service_data()
        request_hash = idempotency.fingerprint({**data, "lines": sorted(data["lines"]), "slug": slug})

        stored = idempotency.find_replay(restaurant, IdempotencyScope.ORDER_CREATE, key, request_hash)
        if stored:
            return idempotency.replay_response(stored)
        try:
            with transaction.atomic():
                order = create_order(restaurant, data)
                order.token = make_token(order)
                body = OrderCreatedSerializer(order).data
                idempotency.remember(restaurant, IdempotencyScope.ORDER_CREATE, key, request_hash, 201, body)
        except IntegrityError:
            # A concurrent request with the same key committed first: answer with its result.
            stored = idempotency.find_replay(restaurant, IdempotencyScope.ORDER_CREATE, key, request_hash)
            if stored:
                return idempotency.replay_response(stored)
            raise
        return Response(body, status=201, headers=PRIVATE_HEADERS)


class PublicOrderView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "order_lookup"

    @extend_schema(parameters=[TOKEN_PARAM], responses=PublicOrderSerializer, summary="Look up your order by its link token")
    def get(self, request, token):
        return Response(PublicOrderSerializer(load_order(token)).data, headers=PRIVATE_HEADERS)


class PublicOrderCancelView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "order_cancel"

    @extend_schema(parameters=[TOKEN_PARAM], request=None, responses=PublicOrderSerializer, summary="Cancel your order while it is still pending")
    def post(self, request, token):
        order = load_order(token)
        change_status(order=order, to_status=OrderStatus.CANCELLED, actor_type=ActorType.CUSTOMER)
        return Response(PublicOrderSerializer(load_order(token)).data, headers=PRIVATE_HEADERS)
