"""Rules the database enforces on its own, even if application code were bypassed."""
import pytest
from django.db import IntegrityError, transaction

from apps.orders.models import Order, OrderItem, OrderStatusEvent, Payment
from apps.orders.tokens import make_token, parse_token, verify_token

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(order_in):
    return order_in()


def test_an_order_cannot_be_paid_before_it_is_served(order):
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(payment_status="PAID")


def test_a_table_number_only_exists_for_dine_in(order):
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(table_number="7")  # the order is pickup


@pytest.mark.parametrize("field, value", [("status", "DONE"), ("payment_status", "MAYBE"), ("fulfilment_type", "DELIVERY"), ("total", -1)])
def test_enumerations_and_amounts_are_checked(order, field, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.filter(pk=order.pk).update(**{field: value})


def test_an_order_number_is_unique_per_restaurant_per_day(order, shop):
    with pytest.raises(IntegrityError), transaction.atomic():
        Order.objects.create(
            restaurant=shop.restaurant, business_date=order.business_date, order_number=order.order_number,
            fulfilment_type="PICKUP", customer_name="x", customer_phone="1234567", currency="USD", subtotal=0, total=0,
        )


def test_a_line_total_must_equal_price_times_quantity(order):
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.filter(order=order).update(line_total="1.00")


@pytest.mark.parametrize("quantity", [0, 100])
def test_quantity_is_between_1_and_99(order, quantity):
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.filter(order=order).update(quantity=quantity, line_total=0)


def test_an_item_cannot_appear_twice_on_one_order(order, shop):
    line = order.items.get()
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(
            order=order, restaurant=order.restaurant, menu_item=line.menu_item, item_name="x", unit_name="u",
            unit_price=1, quantity=1, line_total=1,
        )


def test_an_order_line_must_point_at_an_item_of_the_same_restaurant(order, make_restaurant, make_category, make_item):
    foreign_item = make_item(make_category(make_restaurant()))
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(
            order=order, restaurant=order.restaurant, menu_item=foreign_item, item_name="x", unit_name="u",
            unit_price=1, quantity=1, line_total=1,
        )


def test_children_must_belong_to_the_orders_restaurant(order, make_restaurant, make_user):
    other = make_restaurant()
    user = make_user()
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderStatusEvent.objects.create(order=order, restaurant=other, to_status="PENDING", actor_type="STAFF")
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(order=order, restaurant=other, amount=5, currency="USD", method="CASH", recorded_by=user)


def test_an_order_has_at_most_one_recorded_payment(order, make_user):
    Order.objects.filter(pk=order.pk).update(status="SERVED")
    user = make_user()
    Payment.objects.create(order=order, restaurant=order.restaurant, amount=5, currency="USD", method="CASH", recorded_by=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(order=order, restaurant=order.restaurant, amount=5, currency="USD", method="CASH", recorded_by=user)
    Payment.objects.filter(order=order).update(status="VOIDED")  # a voided payment frees the slot
    Payment.objects.create(order=order, restaurant=order.restaurant, amount=5, currency="USD", method="TRANSFER", recorded_by=user)


def test_payments_must_be_positive(order, make_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(order=order, restaurant=order.restaurant, amount=0, currency="USD", method="CASH", recorded_by=make_user())


# ---------------------------------------------------------------- tokens (no database needed beyond the fixture)
def test_tokens_verify_and_reject_tampering(order):
    token = make_token(order)
    assert len(token) == 96 and parse_token(token) == order.public_id and verify_token(token, order)
    assert not verify_token(token[:32] + "0" * 64, order)
    order.token_version += 1
    assert not verify_token(token, order)


def test_malformed_tokens_do_not_parse():
    for bad in (None, 5, "", "abc", "g" * 96, "A" * 96, "0" * 95, "0" * 97):
        assert parse_token(bad) is None


def test_old_links_survive_key_rotation_when_the_old_key_is_a_fallback(order, settings):
    token = make_token(order)
    settings.SECRET_KEY_FALLBACKS = [settings.SECRET_KEY]
    settings.SECRET_KEY = "a-new-secret-key-for-this-test-only-" + "x" * 30
    assert verify_token(token, order)
    settings.SECRET_KEY_FALLBACKS = []
    assert not verify_token(token, order)
