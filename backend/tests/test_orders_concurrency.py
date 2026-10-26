"""Real concurrent requests against PostgreSQL (each thread has its own connection)."""
import threading
import uuid

import pytest
from django.db import connections
from django.urls import reverse
from rest_framework.test import APIClient

from apps.orders.models import Order, Payment

pytestmark = pytest.mark.django_db(transaction=True)


def run_in_threads(jobs):
    results = [None] * len(jobs)

    def worker(index, job):
        try:
            results[index] = job()
        except Exception as exc:  # reported by the assertions below
            results[index] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i, job)) for i, job in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def test_simultaneous_orders_get_distinct_codes(shop):
    url = reverse("public-order-create", kwargs={"slug": shop.restaurant.slug})

    def job(n):
        def place():
            body = {
                "customer_name": "Ada", "customer_phone": f"+44207946{n:04d}", "fulfilment_type": "PICKUP",
                "items": [{"menu_item_id": shop.rice.pk, "quantity": 1}],
            }
            return APIClient().post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex).status_code
        return place

    results = run_in_threads([job(n) for n in range(6)])

    assert results == [201] * 6
    assert sorted(Order.objects.values_list("order_number", flat=True)) == [1, 2, 3, 4, 5, 6]


def test_the_same_key_sent_at_once_creates_one_order(shop):
    url = reverse("public-order-create", kwargs={"slug": shop.restaurant.slug})
    body = {
        "customer_name": "Ada", "customer_phone": "+442079460958", "fulfilment_type": "PICKUP",
        "items": [{"menu_item_id": shop.rice.pk, "quantity": 1}],
    }
    key = uuid.uuid4().hex

    results = run_in_threads([
        lambda: APIClient().post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key).json() for _ in range(4)
    ])

    assert Order.objects.count() == 1
    assert all(not isinstance(r, Exception) for r in results), results
    assert len({r["token"] for r in results}) == 1


def test_two_staff_paying_the_same_order_record_one_payment(shop, order_in, make_user, make_membership):
    order = order_in("SERVED")
    clients = []
    for _ in range(2):
        user = make_user()
        make_membership(shop.restaurant, user)
        client = APIClient()
        client.force_login(user)
        clients.append(client)
    url = reverse("staff-order-payment", kwargs={"slug": shop.restaurant.slug, "public_id": order.public_id})

    results = run_in_threads([
        (lambda c=c: c.post(url, {"method": "CASH", "amount": "5.00"}, format="json", HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex).status_code)
        for c in clients
    ])

    assert sorted(results) == [200, 409]
    assert Payment.objects.count() == 1
