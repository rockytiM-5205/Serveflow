import re

from rest_framework import serializers

from apps.restaurants.models import Restaurant

from .models import Fulfilment, Order, OrderItem, OrderStatus, OrderStatusEvent, Payment, PaymentMethod


def normalize_phone(value):
    """"+44 (20) 7946-0958" -> "+442079460958". 7 to 15 digits, optional leading +."""
    text = re.sub(r"[\s().-]", "", value)
    plus = text.startswith("+")
    digits = text[1:] if plus else text
    if not re.fullmatch(r"[0-9]{7,15}", digits):
        raise serializers.ValidationError("Enter a valid phone number.")
    return ("+" if plus else "") + digits


# ------------------------------------------------------------------ customers
class OrderLineSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=99)


class OrderCreateSerializer(serializers.Serializer):
    """Only ids and quantities are accepted. Anything else a client sends (prices, totals,
    status) is ignored: the server prices the order from the menu."""

    customer_name = serializers.CharField(max_length=80)
    customer_phone = serializers.CharField(max_length=30)
    fulfilment_type = serializers.ChoiceField(choices=Fulfilment.choices)
    table_number = serializers.CharField(max_length=20, required=False, allow_blank=True, allow_null=True, default=None)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    items = OrderLineSerializer(many=True, allow_empty=False, max_length=30)

    def validate_customer_phone(self, value):
        return normalize_phone(value)

    def to_service_data(self):
        data = self.validated_data
        return {
            "customer_name": data["customer_name"],
            "customer_phone": data["customer_phone"],
            "fulfilment_type": data["fulfilment_type"],
            "table_number": data["table_number"],
            "notes": data["notes"],
            "lines": [(line["menu_item_id"], line["quantity"]) for line in data["items"]],
        }


class OrderRestaurantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = ("slug", "name")
        read_only_fields = fields


class PublicOrderItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="item_name")

    class Meta:
        model = OrderItem
        fields = ("name", "unit_name", "unit_price", "quantity", "line_total")
        read_only_fields = fields


class TimelineEntrySerializer(serializers.ModelSerializer):
    status = serializers.CharField(source="to_status")
    at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = OrderStatusEvent
        fields = ("status", "at")
        read_only_fields = fields


class PublicOrderSerializer(serializers.ModelSerializer):
    """What a customer may see about their own order. No name, no phone, no ids."""

    code = serializers.CharField(read_only=True)
    restaurant = OrderRestaurantSerializer(read_only=True)
    items = PublicOrderItemSerializer(many=True, read_only=True)
    timeline = TimelineEntrySerializer(source="events", many=True, read_only=True)
    cancellable = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "code", "status", "payment_status", "fulfilment_type", "table_number", "currency", "subtotal", "total",
            "restaurant", "items", "timeline", "cancellable", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_cancellable(self, order) -> bool:
        return order.status == OrderStatus.PENDING


class OrderCreatedSerializer(PublicOrderSerializer):
    token = serializers.CharField(read_only=True)

    class Meta(PublicOrderSerializer.Meta):
        fields = ("token", *PublicOrderSerializer.Meta.fields)
        read_only_fields = fields


# ------------------------------------------------------------------ staff
class StaffOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("item_name", "unit_name", "unit_price", "quantity", "line_total")
        read_only_fields = fields


class StaffEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor_user.email", read_only=True, default=None)

    class Meta:
        model = OrderStatusEvent
        fields = ("from_status", "to_status", "actor_type", "actor_email", "reason", "created_at")
        read_only_fields = fields


class StaffPaymentSerializer(serializers.ModelSerializer):
    recorded_by_email = serializers.EmailField(source="recorded_by.email", read_only=True)

    class Meta:
        model = Payment
        fields = ("amount", "currency", "method", "status", "reference", "recorded_by_email", "created_at")
        read_only_fields = fields


class StaffOrderListSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)
    items = StaffOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "public_id", "code", "business_date", "status", "payment_status", "fulfilment_type", "table_number",
            "customer_name", "items", "total", "currency", "created_at", "updated_at",
        )
        read_only_fields = fields


class StaffOrderDetailSerializer(StaffOrderListSerializer):
    events = StaffEventSerializer(many=True, read_only=True)
    payments = StaffPaymentSerializer(many=True, read_only=True)

    class Meta(StaffOrderListSerializer.Meta):
        fields = (*StaffOrderListSerializer.Meta.fields, "customer_phone", "notes", "subtotal", "events", "payments")
        read_only_fields = fields


class TransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(
        choices=[OrderStatus.CONFIRMED, OrderStatus.REJECTED, OrderStatus.SERVING, OrderStatus.SERVED]
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    expected_status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    acknowledge_serving = serializers.BooleanField(required=False, default=False)
    expected_status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)


class PaymentSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
