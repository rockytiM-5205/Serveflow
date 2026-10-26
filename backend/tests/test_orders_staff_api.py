"""Staff order queue, status changes, cancellation rules and payments."""
import uuid

import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.orders.models import Order, OrderStatusEvent, Payment
from apps.restaurants.models import MembershipRole

pytestmark = pytest.mark.django_db

STAFF, MANAGER, OWNER = MembershipRole.STAFF, MembershipRole.MANAGER, MembershipRole.OWNER


def url(name, restaurant, order=None):
    kwargs = {"slug": restaurant.slug}
    if order is not None:
        kwargs["public_id"] = order.public_id
    return reverse(name, kwargs=kwargs)


def code(response):
    return response.json()["error"]["code"]


def move(client, shop, order, to_status, **extra):
    return client.post(url("staff-order-transition", shop.restaurant, order), {"to_status": to_status, **extra}, format="json")


def pay(client, shop, order, key=None, **extra):
    body = {"method": "CASH", "amount": "5.00", **extra}
    return client.post(
        url("staff-order-payment", shop.restaurant, order), body, format="json", HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex
    )


# ---------------------------------------------------------------- access and listing
def test_orders_need_a_staff_role_in_the_right_restaurant(api_client, shop, order_in, make_user, make_restaurant):
    order = order_in()
    assert api_client.get(url("staff-orders", shop.restaurant)).status_code == 401
    api_client.force_login(make_user())
    assert api_client.get(url("staff-orders", shop.restaurant)).status_code == 403
    assert api_client.get(url("staff-order", shop.restaurant, order)).status_code == 403


def test_lists_hold_only_the_callers_orders(api_client, shop, order_in, staff_login, make_restaurant, make_category, make_item, place):
    mine = order_in()
    other = make_restaurant(accepting_orders=True)
    place(other, [(make_item(make_category(other)).pk, 1)])
    staff_login(shop.restaurant, STAFF)
    body = api_client.get(url("staff-orders", shop.restaurant)).json()
    assert [o["public_id"] for o in body["results"]] == [str(mine.public_id)]
    assert set(body) == {"next", "previous", "results"}


def test_the_list_shows_what_the_kitchen_needs_but_not_the_phone(api_client, shop, order_in, staff_login):
    order_in()
    staff_login(shop.restaurant, STAFF)
    row = api_client.get(url("staff-orders", shop.restaurant)).json()["results"][0]
    assert row["code"] == "001" and row["customer_name"] == "Ada" and row["total"] == "5.00"
    assert row["items"][0]["item_name"] == "Rice" and row["items"][0]["quantity"] == 2
    assert "customer_phone" not in row


def test_filters(api_client, shop, order_in, staff_login):
    pending = order_in(phone="+442079460001")
    served_unpaid = order_in("SERVED", phone="+442079460002")
    served_paid = order_in("SERVED", phone="+442079460003")
    Order.objects.filter(pk=served_paid.pk).update(payment_status="PAID")
    cancelled = order_in("CANCELLED", phone="+442079460004")
    staff_login(shop.restaurant, STAFF)
    list_url = url("staff-orders", shop.restaurant)

    def ids(**params):
        return {o["public_id"] for o in api_client.get(list_url, params).json()["results"]}

    assert ids(queue="1") == {str(pending.public_id), str(served_unpaid.public_id)}
    assert ids(status="SERVED") == {str(served_unpaid.public_id), str(served_paid.public_id)}
    assert ids(status="PENDING,CANCELLED") == {str(pending.public_id), str(cancelled.public_id)}
    assert ids(payment_status="PAID") == {str(served_paid.public_id)}
    assert ids(code="2") == {str(served_unpaid.public_id)}
    assert ids(fulfilment_type="DINE_IN") == set()
    assert ids(business_date=str(pending.business_date)) and not ids(business_date="1999-01-01")
    assert ids(business_date="not-a-date") == set()


def test_detail_includes_the_phone_and_the_history(api_client, shop, order_in, staff_login):
    order = order_in()
    staff_login(shop.restaurant, STAFF)
    body = api_client.get(url("staff-order", shop.restaurant, order)).json()
    assert body["customer_phone"] == "+442079460958" and body["subtotal"] == "5.00"
    assert [e["to_status"] for e in body["events"]] == ["PENDING"] and body["events"][0]["actor_type"] == "CUSTOMER"
    assert body["payments"] == []


def test_another_restaurants_orders_are_404_everywhere(api_client, shop, order_in, staff_login, make_restaurant):
    order = order_in("SERVED")
    mine = make_restaurant()
    staff_login(mine, OWNER)
    for name in ("staff-order",):
        assert api_client.get(url(name, mine, order)).status_code == 404
    for name in ("staff-order-transition", "staff-order-cancel", "staff-order-payment"):
        response = api_client.post(url(name, mine, order), {"to_status": "SERVING", "reason": "x", "method": "CASH", "amount": "5.00"},
                                   format="json", HTTP_IDEMPOTENCY_KEY="k" * 20)
        assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == "SERVED" and order.payment_status == "UNPAID"


# ---------------------------------------------------------------- status changes
def test_an_order_moves_through_its_whole_life_and_every_step_is_recorded(api_client, shop, order_in, staff_login):
    order = order_in()
    user = staff_login(shop.restaurant, STAFF)
    for step in ("CONFIRMED", "SERVING", "SERVED"):
        response = move(api_client, shop, order, step)
        assert response.status_code == 200 and response.json()["status"] == step
    events = list(OrderStatusEvent.objects.filter(order=order).values_list("from_status", "to_status", "actor_type", "actor_user"))
    assert events == [
        (None, "PENDING", "CUSTOMER", None), ("PENDING", "CONFIRMED", "STAFF", user.pk),
        ("CONFIRMED", "SERVING", "STAFF", user.pk), ("SERVING", "SERVED", "STAFF", user.pk),
    ]


def test_steps_cannot_be_skipped_or_reversed(api_client, shop, order_in, staff_login):
    order = order_in()
    staff_login(shop.restaurant, STAFF)
    skip = move(api_client, shop, order, "SERVED")
    assert skip.status_code == 409 and code(skip) == "invalid_transition"
    move(api_client, shop, order, "CONFIRMED")
    back = move(api_client, shop, order, "CONFIRMED")
    assert back.status_code == 409 and code(back) == "invalid_transition"


def test_cancelling_is_not_a_plain_transition(api_client, shop, order_in, staff_login):
    order = order_in()
    staff_login(shop.restaurant, STAFF)
    assert move(api_client, shop, order, "CANCELLED", reason="x").status_code == 400
    assert move(api_client, shop, order, "PENDING").status_code == 400


def test_rejecting_needs_a_reason(api_client, shop, order_in, staff_login):
    order = order_in()
    staff_login(shop.restaurant, STAFF)
    missing = move(api_client, shop, order, "REJECTED")
    assert missing.status_code == 400 and "reason" in missing.json()["error"]["details"]
    ok = move(api_client, shop, order, "REJECTED", reason="Kitchen is closed")
    assert ok.status_code == 200 and OrderStatusEvent.objects.latest("id").reason == "Kitchen is closed"


def test_acting_on_a_stale_view_is_refused(api_client, shop, order_in, staff_login):
    order = order_in()
    staff_login(shop.restaurant, STAFF)
    Order.objects.filter(pk=order.pk).update(status="CONFIRMED")  # someone else got there first
    response = move(api_client, shop, order, "CONFIRMED", expected_status="PENDING")
    assert response.status_code == 409 and code(response) == "stale_status"
    assert response.json()["error"]["details"] == {"current_status": "CONFIRMED"}


# ---------------------------------------------------------------- cancellation
def cancel(client, shop, order, **body):
    return client.post(url("staff-order-cancel", shop.restaurant, order), body, format="json")


@pytest.mark.parametrize("status", ["PENDING", "CONFIRMED"])
def test_staff_can_cancel_before_serving_with_a_reason(api_client, shop, order_in, staff_login, status):
    order = order_in(status)
    user = staff_login(shop.restaurant, STAFF)
    assert cancel(api_client, shop, order).status_code == 400  # reason is required
    response = cancel(api_client, shop, order, reason="Customer called")
    assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    event = OrderStatusEvent.objects.latest("id")
    assert (event.actor_type, event.actor_user, event.reason) == ("STAFF", user, "Customer called")


def test_staff_cannot_cancel_an_order_being_served(api_client, shop, order_in, staff_login):
    order = order_in("SERVING")
    staff_login(shop.restaurant, STAFF)
    response = cancel(api_client, shop, order, reason="x", acknowledge_serving=True)
    assert response.status_code == 403 and code(response) == "manager_required"
    order.refresh_from_db()
    assert order.status == "SERVING"


@pytest.mark.parametrize("role", [MANAGER, OWNER])
def test_managers_and_owners_can_cancel_while_serving_only_with_acknowledgement(api_client, shop, order_in, staff_login, role):
    order = order_in("SERVING")
    user = staff_login(shop.restaurant, role)
    unconfirmed = cancel(api_client, shop, order, reason="Spilled")
    assert unconfirmed.status_code == 400 and "acknowledge_serving" in unconfirmed.json()["error"]["details"]
    response = cancel(api_client, shop, order, reason="Spilled", acknowledge_serving=True)
    assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    entry = AuditLog.objects.get(action="order.cancelled_while_serving")
    assert entry.actor == user and entry.metadata == {"code": "001", "reason": "Spilled"}
    assert OrderStatusEvent.objects.latest("id").actor_type == role


@pytest.mark.parametrize("status", ["SERVED", "REJECTED", "CANCELLED"])
def test_finished_orders_cannot_be_cancelled(api_client, shop, order_in, staff_login, status):
    order = order_in(status)
    staff_login(shop.restaurant, OWNER)
    response = cancel(api_client, shop, order, reason="x", acknowledge_serving=True)
    assert response.status_code == 409 and code(response) == "invalid_transition"


# ---------------------------------------------------------------- payments
def test_payment_is_recorded_once_for_the_exact_total(api_client, shop, order_in, staff_login):
    order = order_in("SERVED")
    user = staff_login(shop.restaurant, STAFF)

    response = pay(api_client, shop, order, reference="TRX-1")

    assert response.status_code == 200
    body = response.json()
    assert body["payment_status"] == "PAID" and body["payments"][0]["amount"] == "5.00"
    assert body["payments"][0]["recorded_by_email"] == user.email
    payment = Payment.objects.get()
    assert (payment.amount, payment.method, payment.currency, payment.reference) == (5, "CASH", "USD", "TRX-1")
    entry = AuditLog.objects.get(action="payment.recorded")
    assert entry.metadata == {"code": "001", "amount": "5.00", "method": "CASH"}


def test_payment_waits_until_the_order_is_served(api_client, shop, order_in, staff_login):
    staff_login(shop.restaurant, STAFF)
    for status in ("PENDING", "CONFIRMED", "SERVING", "CANCELLED", "REJECTED"):
        response = pay(api_client, shop, order_in(status, phone=f"+4420794600{len(status):02d}"))
        assert response.status_code == 409 and code(response) == "not_payable", status
    assert not Payment.objects.exists()


@pytest.mark.parametrize("amount", ["4.99", "5.01", "0", "50.00"])
def test_the_amount_must_equal_the_total(api_client, shop, order_in, staff_login, amount):
    order = order_in("SERVED")
    staff_login(shop.restaurant, STAFF)
    response = pay(api_client, shop, order, amount=amount)
    assert response.status_code == 400 and "amount" in response.json()["error"]["details"]
    assert not Payment.objects.exists()


def test_a_second_payment_with_a_new_key_is_refused(api_client, shop, order_in, staff_login):
    order = order_in("SERVED")
    staff_login(shop.restaurant, STAFF)
    pay(api_client, shop, order)
    again = pay(api_client, shop, order)
    assert again.status_code == 409 and code(again) == "already_paid"
    assert Payment.objects.count() == 1


def test_retrying_a_payment_with_the_same_key_returns_the_first_answer(api_client, shop, order_in, staff_login):
    order = order_in("SERVED")
    staff_login(shop.restaurant, STAFF)
    first = pay(api_client, shop, order, key="p" * 20)
    retry = pay(api_client, shop, order, key="p" * 20)
    assert retry.status_code == 200 and retry.json() == first.json()
    assert retry.headers["Idempotent-Replay"] == "true"
    assert Payment.objects.count() == 1
    clash = pay(api_client, shop, order, key="p" * 20, method="TRANSFER")
    assert clash.status_code == 409 and code(clash) == "idempotency_key_reused"


def test_payment_needs_an_idempotency_key_and_a_valid_method(api_client, shop, order_in, staff_login):
    order = order_in("SERVED")
    staff_login(shop.restaurant, STAFF)
    no_key = api_client.post(url("staff-order-payment", shop.restaurant, order), {"method": "CASH", "amount": "5.00"}, format="json")
    assert no_key.status_code == 400 and code(no_key) == "idempotency_key_required"
    assert pay(api_client, shop, order, method="BITCOIN").status_code == 400


def test_a_paid_order_stays_paid_and_served(api_client, shop, order_in, staff_login):
    order = order_in("SERVED")
    staff_login(shop.restaurant, OWNER)
    pay(api_client, shop, order)
    assert cancel(api_client, shop, order, reason="x", acknowledge_serving=True).status_code == 409
    order.refresh_from_db()
    assert (order.status, order.payment_status) == ("SERVED", "PAID")
