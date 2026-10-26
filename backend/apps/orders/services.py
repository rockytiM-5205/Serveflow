"""Creating orders and recording payments. Prices always come from the database, never the client."""
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.common.exceptions import Conflict
from apps.menu.models import MenuItem
from apps.restaurants.models import Restaurant

from .models import (
    ActorType, DailyOrderCounter, Fulfilment, Order, OrderItem, OrderStatus, OrderStatusEvent,
    Payment, PaymentStatus,
)

MAX_OPEN_ORDERS_PER_PHONE = 3
MAX_QUANTITY_PER_ITEM = 99


def business_date_for(restaurant):
    return timezone.now().astimezone(ZoneInfo(restaurant.timezone)).date()


def next_order_number(restaurant, business_date):
    """Next short code for the day. The counter row is locked until the order commits."""
    counter, _ = DailyOrderCounter.objects.select_for_update().get_or_create(
        restaurant=restaurant, business_date=business_date, defaults={"last_number": 0}
    )
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return counter.last_number


@transaction.atomic
def create_order(restaurant, data):
    """data: customer_name, customer_phone, fulfilment_type, table_number, notes, lines=[(menu_item_id, qty)]."""
    restaurant = Restaurant.objects.get(pk=restaurant.pk)  # fresh switches, not the ones read earlier
    if not restaurant.accepting_orders:
        raise Conflict("This restaurant isn't taking orders right now.", code="not_accepting_orders")

    fulfilment = data["fulfilment_type"]
    allowed = {Fulfilment.PICKUP: restaurant.pickup_enabled, Fulfilment.DINE_IN: restaurant.dine_in_enabled}
    if not allowed[fulfilment]:
        raise Conflict("This restaurant doesn't offer that option.", code="fulfilment_disabled")
    table_number = (data.get("table_number") or "").strip() or None
    if fulfilment == Fulfilment.DINE_IN:
        if restaurant.requires_table_number and not table_number:
            raise ValidationError({"table_number": ["Enter your table number."]})
    else:
        table_number = None

    quantities = {}
    for item_id, quantity in data["lines"]:
        quantities[item_id] = quantities.get(item_id, 0) + quantity
    if any(q > MAX_QUANTITY_PER_ITEM for q in quantities.values()):
        raise ValidationError({"items": [f"You can order at most {MAX_QUANTITY_PER_ITEM} of one item."]})

    open_orders = Order.objects.filter(
        restaurant=restaurant, customer_phone=data["customer_phone"], status=OrderStatus.PENDING
    ).count()
    if open_orders >= MAX_OPEN_ORDERS_PER_PHONE:
        raise Conflict("You already have several orders waiting. Please wait for the restaurant to respond.", code="too_many_open_orders")

    orderable = {
        item.pk: item
        for item in MenuItem.objects.filter(
            restaurant=restaurant, pk__in=list(quantities), archived_at__isnull=True, category__is_active=True
        )
    }
    problems = []
    for item_id in quantities:
        item = orderable.get(item_id)
        if item is None:
            problems.append({"id": item_id, "reason": "not_found"})  # also covers other restaurants' items
        elif not item.is_available:
            problems.append({"id": item_id, "name": item.name, "reason": "unavailable"})
    if problems:
        raise Conflict("Some items can't be ordered any more.", code="item_unavailable", details={"items": problems})

    lines, subtotal = [], Decimal("0.00")
    for item_id, quantity in quantities.items():
        item = orderable[item_id]
        line_total = (item.price * quantity).quantize(Decimal("0.01"))
        subtotal += line_total
        lines.append((item, quantity, line_total))

    business_date = business_date_for(restaurant)
    order = Order.objects.create(
        restaurant=restaurant, business_date=business_date, order_number=next_order_number(restaurant, business_date),
        fulfilment_type=fulfilment, table_number=table_number, customer_name=data["customer_name"],
        customer_phone=data["customer_phone"], notes=data.get("notes", ""), currency=restaurant.currency,
        subtotal=subtotal, total=subtotal,
    )
    OrderItem.objects.bulk_create(
        OrderItem(
            order=order, restaurant=restaurant, menu_item=item, item_name=item.name, unit_name=item.unit_name,
            unit_price=item.price, quantity=quantity, line_total=line_total,
        )
        for item, quantity, line_total in lines
    )
    OrderStatusEvent.objects.create(
        order=order, restaurant=restaurant, from_status=None, to_status=OrderStatus.PENDING, actor_type=ActorType.CUSTOMER
    )
    return order


def record_payment(*, order, actor_user, method, amount, reference=""):
    """Record full payment for a served order. One payment per order; the amount must equal the total."""
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.payment_status == PaymentStatus.PAID:
            raise Conflict("This order is already paid.", code="already_paid")
        if locked.status != OrderStatus.SERVED:
            raise Conflict(
                "Payment can be recorded once the order has been served.", code="not_payable", details={"status": locked.status}
            )
        if amount != locked.total:
            raise ValidationError({"amount": [f"The amount must equal the order total ({locked.total})."]})
        Payment.objects.create(
            order=locked, restaurant=locked.restaurant, amount=amount, currency=locked.currency, method=method,
            reference=reference, recorded_by=actor_user,
        )
        locked.payment_status = PaymentStatus.PAID
        locked.save(update_fields=["payment_status", "updated_at"])
        record(
            restaurant=locked.restaurant, actor=actor_user, action="payment.recorded", entity_type="order",
            entity_id=locked.pk, metadata={"code": locked.code, "amount": str(amount), "method": method},
        )
    return locked
