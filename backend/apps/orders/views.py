"""Staff order endpoints, mounted under /restaurants/<slug>/ (tenant-scoped, role-checked)."""
from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView, ListAPIView, RetrieveAPIView
from rest_framework.response import Response

from apps.common.pagination import DefaultCursorPagination
from apps.common.schema import SLUG_PARAM, staff_schema
from apps.restaurants.models import MembershipRole
from apps.restaurants.permissions import RestaurantScopedMixin

from . import idempotency
from .models import IdempotencyScope, Order, OrderStatus, PaymentStatus
from .public_views import IDEMPOTENCY_PARAM
from .serializers import (
    CancelSerializer, PaymentSerializer, StaffOrderDetailSerializer, StaffOrderListSerializer, TransitionSerializer,
)
from .services import record_payment
from .workflow import actor_type_for, change_status

STAFF = MembershipRole.STAFF
OPEN_STATUSES = [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.SERVING]


class OrderPagination(DefaultCursorPagination):
    ordering = ("-created_at", "-id")


def load_detail(restaurant, public_id):
    return (
        Order.objects.filter(restaurant=restaurant, public_id=public_id)
        .prefetch_related("items", "payments__recorded_by", "events__actor_user")
        .get()
    )


FILTERS = [
    OpenApiParameter("status", str, description="Comma-separated statuses, e.g. PENDING,CONFIRMED"),
    OpenApiParameter("payment_status", str, description="UNPAID or PAID"),
    OpenApiParameter("fulfilment_type", str, description="PICKUP or DINE_IN"),
    OpenApiParameter("business_date", str, description="YYYY-MM-DD in the restaurant's timezone"),
    OpenApiParameter("code", int, description="Order code, e.g. 42 for #042"),
    OpenApiParameter("queue", int, description="1 = orders that still need attention: open, or served but unpaid"),
]


@staff_schema(extra_parameters=FILTERS, get="List orders, newest first")
class OrderListView(RestaurantScopedMixin, ListAPIView):
    min_role = STAFF
    queryset = Order.objects.prefetch_related("items")
    serializer_class = StaffOrderListSerializer
    pagination_class = OrderPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset
        params = self.request.query_params
        statuses = [s for s in params.get("status", "").split(",") if s in OrderStatus.values]
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        if params.get("payment_status") in PaymentStatus.values:
            queryset = queryset.filter(payment_status=params["payment_status"])
        if params.get("fulfilment_type") in ("PICKUP", "DINE_IN"):
            queryset = queryset.filter(fulfilment_type=params["fulfilment_type"])
        try:
            if params.get("business_date"):
                queryset = queryset.filter(business_date=date.fromisoformat(params["business_date"]))
        except ValueError:
            queryset = queryset.none()
        code = params.get("code", "")
        if code.isdigit() and len(code) <= 9:
            queryset = queryset.filter(order_number=int(code))
        if params.get("queue") == "1":
            queryset = queryset.filter(
                Q(status__in=OPEN_STATUSES) | Q(status=OrderStatus.SERVED, payment_status=PaymentStatus.UNPAID)
            )
        return queryset


@staff_schema(get="Order details, including the customer's phone number and the full history")
class OrderDetailView(RestaurantScopedMixin, RetrieveAPIView):
    min_role = STAFF
    queryset = Order.objects.prefetch_related("items", "payments__recorded_by", "events__actor_user")
    serializer_class = StaffOrderDetailSerializer
    lookup_field = "public_id"


class OrderActionView(RestaurantScopedMixin, GenericAPIView):
    """Base for actions on one order. The order is looked up inside the caller's restaurant only."""

    min_role = STAFF
    queryset = Order.objects.all()
    lookup_field = "public_id"
    http_method_names = ["post", "options"]

    def detail_response(self, order):
        return Response(StaffOrderDetailSerializer(load_detail(self.request.restaurant, order.public_id)).data)


class OrderTransitionView(OrderActionView):
    serializer_class = TransitionSerializer

    @extend_schema(
        parameters=[SLUG_PARAM], request=TransitionSerializer, responses=StaffOrderDetailSerializer,
        summary="Confirm, reject, start serving or mark served. Send expected_status to avoid acting on a stale view.",
    )
    def post(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        change_status(
            order=order, to_status=data["to_status"], actor_type=actor_type_for(request.membership.role),
            actor_user=request.user, reason=data["reason"], expected_status=data.get("expected_status"),
        )
        return self.detail_response(order)


class OrderCancelView(OrderActionView):
    serializer_class = CancelSerializer

    @extend_schema(
        parameters=[SLUG_PARAM], request=CancelSerializer, responses=StaffOrderDetailSerializer,
        summary="Cancel an order with a reason. While it is being served this needs a manager or owner and acknowledge_serving.",
    )
    def post(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        change_status(
            order=order, to_status=OrderStatus.CANCELLED, actor_type=actor_type_for(request.membership.role),
            actor_user=request.user, reason=data["reason"], expected_status=data.get("expected_status"),
            acknowledge_serving=data["acknowledge_serving"],
        )
        return self.detail_response(order)


class OrderPaymentView(OrderActionView):
    serializer_class = PaymentSerializer

    @extend_schema(
        parameters=[SLUG_PARAM, IDEMPOTENCY_PARAM], request=PaymentSerializer, responses=StaffOrderDetailSerializer,
        summary="Record full payment for a served order (cash or transfer received). One payment per order.",
    )
    def post(self, request, *args, **kwargs):
        order = self.get_object()
        key = idempotency.read_key(request)
        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_hash = idempotency.fingerprint({
            "order": str(order.public_id), "method": data["method"], "amount": str(data["amount"]),
            "reference": data["reference"],
        })
        restaurant = request.restaurant
        stored = idempotency.find_replay(restaurant, IdempotencyScope.PAYMENT_RECORD, key, request_hash)
        if stored:
            return idempotency.replay_response(stored)
        try:
            with transaction.atomic():
                record_payment(
                    order=order, actor_user=request.user, method=data["method"], amount=data["amount"],
                    reference=data["reference"],
                )
                body = StaffOrderDetailSerializer(load_detail(restaurant, order.public_id)).data
                idempotency.remember(restaurant, IdempotencyScope.PAYMENT_RECORD, key, request_hash, 200, body)
        except IntegrityError:
            stored = idempotency.find_replay(restaurant, IdempotencyScope.PAYMENT_RECORD, key, request_hash)
            if stored:
                return idempotency.replay_response(stored)
            raise
        return Response(body)
