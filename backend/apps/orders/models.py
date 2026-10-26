"""Orders and payments.

Rules enforced by the database as well as the services:
- an order, its items, its events and its payments all belong to the same restaurant
  (composite foreign keys, added in the hand-written migration 0002);
- totals are decimals, and an item line's total equals unit price x quantity;
- an order can only be PAID once SERVED, and a table number only exists for dine-in;
- an order has at most one recorded payment.
Customers are guests: an order is reached through a signed token, never a database id.
"""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.menu.models import MenuItem
from apps.restaurants.models import Restaurant


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    SERVING = "SERVING", "Being served"
    SERVED = "SERVED", "Served"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PAID = "PAID", "Paid"


class Fulfilment(models.TextChoices):
    PICKUP = "PICKUP", "Pickup"
    DINE_IN = "DINE_IN", "Dine in"


class ActorType(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    STAFF = "STAFF", "Staff"
    MANAGER = "MANAGER", "Manager"
    OWNER = "OWNER", "Owner"
    SYSTEM = "SYSTEM", "System"


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    TRANSFER = "TRANSFER", "Bank transfer"


class PaymentRecordStatus(models.TextChoices):
    RECORDED = "RECORDED", "Recorded"
    VOIDED = "VOIDED", "Voided"  # reserved: there is no endpoint to void a payment yet


class IdempotencyScope(models.TextChoices):
    ORDER_CREATE = "ORDER_CREATE", "Order creation"
    PAYMENT_RECORD = "PAYMENT_RECORD", "Payment recording"


class DailyOrderCounter(models.Model):
    """Last order number handed out per restaurant per local day (numbers restart each day)."""

    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name="+")
    business_date = models.DateField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "business_date"], name="orders_counter_unique_day"),
        ]


class Order(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name="orders")
    business_date = models.DateField(help_text="The restaurant's local date when the order was placed.")
    order_number = models.PositiveIntegerField(help_text="Short code staff call out; restarts every day.")
    status = models.CharField(max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    payment_status = models.CharField(max_length=8, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    fulfilment_type = models.CharField(max_length=8, choices=Fulfilment.choices)
    table_number = models.CharField(max_length=20, null=True, blank=True)
    customer_name = models.CharField(max_length=80)
    customer_phone = models.CharField(max_length=20)
    notes = models.CharField(max_length=500, blank=True)
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    token_version = models.PositiveSmallIntegerField(default=1, help_text="Raise to invalidate the customer's link.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "business_date", "order_number"], name="orders_order_unique_number_per_day"),
            models.UniqueConstraint(fields=["id", "restaurant"], name="orders_order_id_restaurant_uniq"),
            models.CheckConstraint(condition=Q(status__in=OrderStatus.values), name="orders_order_status_valid"),
            models.CheckConstraint(condition=Q(payment_status__in=PaymentStatus.values), name="orders_order_payment_status_valid"),
            models.CheckConstraint(condition=Q(fulfilment_type__in=Fulfilment.values), name="orders_order_fulfilment_valid"),
            models.CheckConstraint(condition=Q(subtotal__gte=0) & Q(total__gte=0), name="orders_order_amounts_non_negative"),
            models.CheckConstraint(
                condition=Q(fulfilment_type="DINE_IN") | Q(table_number__isnull=True), name="orders_order_table_only_dine_in"
            ),
            models.CheckConstraint(
                condition=Q(payment_status="UNPAID") | Q(status="SERVED"), name="orders_order_paid_only_when_served"
            ),
        ]
        indexes = [
            models.Index(fields=["restaurant", "-created_at"], name="orders_order_recent_idx"),
            models.Index(fields=["restaurant", "status"], name="orders_order_status_idx"),
        ]

    def __str__(self):
        return f"#{self.code} ({self.restaurant.slug})"

    @property
    def code(self):
        return f"{self.order_number:03d}"


class OrderItem(models.Model):
    """What was ordered, frozen at order time: renaming or repricing the menu never changes history."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name="+")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="+")
    item_name = models.CharField(max_length=120)
    unit_name = models.CharField(max_length=32)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(99)])
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "menu_item"], name="orders_item_unique_per_order"),
            models.CheckConstraint(condition=Q(quantity__gte=1) & Q(quantity__lte=99), name="orders_item_quantity_range"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="orders_item_price_non_negative"),
            models.CheckConstraint(
                condition=Q(line_total=F("unit_price") * F("quantity")), name="orders_item_line_total_matches"
            ),
        ]


class OrderStatusEvent(models.Model):
    """Append-only history of an order's status. The admin shows it read-only."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=16, choices=OrderStatus.choices, null=True, blank=True)
    to_status = models.CharField(max_length=16, choices=OrderStatus.choices)
    actor_type = models.CharField(max_length=8, choices=ActorType.choices)
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(to_status__in=OrderStatus.values), name="orders_event_status_valid"),
            models.CheckConstraint(condition=Q(actor_type__in=ActorType.values), name="orders_event_actor_valid"),
        ]


class Payment(models.Model):
    """A payment staff recorded after receiving it. This is a record, not verification of a transfer."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    method = models.CharField(max_length=8, choices=PaymentMethod.choices)
    status = models.CharField(max_length=8, choices=PaymentRecordStatus.choices, default=PaymentRecordStatus.RECORDED)
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order"], condition=Q(status="RECORDED"), name="orders_payment_one_recorded_per_order"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="orders_payment_amount_positive"),
            models.CheckConstraint(condition=Q(method__in=PaymentMethod.values), name="orders_payment_method_valid"),
            models.CheckConstraint(condition=Q(status__in=PaymentRecordStatus.values), name="orders_payment_status_valid"),
        ]


class IdempotencyKey(models.Model):
    """Remembers the answer to a request so a retry cannot create a second order or payment."""

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="+")
    scope = models.CharField(max_length=16, choices=IdempotencyScope.choices)
    key = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "scope", "key"], name="orders_idempotency_unique_key"),
        ]
        indexes = [models.Index(fields=["created_at"], name="orders_idem_created_idx")]
