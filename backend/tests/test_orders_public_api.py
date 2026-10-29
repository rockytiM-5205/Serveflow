"""Guest ordering: server-side pricing, idempotency, tokens. Need PostgreSQL and the migrations."""
import pytest
from django.urls import reverse

from apps.orders.models import Order, OrderStatusEvent

pytestmark = pytest.mark.django_db

KEY = "k" * 20


def code(response):
    return response.json()["error"]["code"]


def lookup(client, token):
    return client.get(reverse("public-order", kwargs={"token": token}))


# ---------------------------------------------------------------- creating
def test_the_server_prices_the_order_and_ignores_client_values(place, shop):
    response = place(
        shop.restaurant, [(shop.rice.pk, 3), (shop.beans.pk, 2)],
        price="0.01", total="0.01", subtotal="0.01", status="SERVED", payment_status="PAID",
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["subtotal"], body["total"], body["currency"]) == ("10.00", "10.00", "USD")
    assert (body["status"], body["payment_status"], body["code"]) == ("PENDING", "UNPAID", "001")
    assert len(body["token"]) == 96
    assert body["cancellable"] is True
    assert [(i["name"], i["quantity"], i["unit_price"], i["line_total"]) for i in body["items"]] == [
        ("Rice", 3, "2.50", "7.50"), ("Beans", 2, "1.25", "2.50"),
    ]
    assert [e["status"] for e in body["timeline"]] == ["PENDING"]
    order = Order.objects.get()
    assert order.customer_name == "Ada" and order.customer_phone == "+442079460958"
    assert OrderStatusEvent.objects.get().actor_type == "CUSTOMER"


def test_the_response_never_contains_personal_details(place, shop):
    body = place(shop.restaurant, [(shop.rice.pk, 1)], notes="No salt").json()
    text = str(body)
    assert "Ada" not in text and "442079460958" not in text
    assert not {"customer_name", "customer_phone", "notes", "id", "public_id"} & set(body)


def test_the_order_keeps_the_price_it_was_placed_at(place, shop, api_client):
    body = place(shop.restaurant, [(shop.rice.pk, 2)]).json()
    shop.rice.price = "9.99"
    shop.rice.name = "Renamed"
    shop.rice.save()
    seen = lookup(api_client, body["token"]).json()
    assert seen["total"] == "5.00" and seen["items"][0]["name"] == "Rice" and seen["items"][0]["unit_price"] == "2.50"


def test_duplicate_lines_are_merged(place, shop):
    body = place(shop.restaurant, [(shop.rice.pk, 2), (shop.rice.pk, 3)]).json()
    assert [(i["name"], i["quantity"]) for i in body["items"]] == [("Rice", 5)]
    assert body["total"] == "12.50"


def test_merged_quantity_is_capped(place, shop):
    response = place(shop.restaurant, [(shop.rice.pk, 60), (shop.rice.pk, 60)])
    assert response.status_code == 400 and "items" in response.json()["error"]["details"]


@pytest.mark.parametrize(
    "override",
    [
        {"items": []},
        {"customer_name": ""},
        {"customer_phone": "123"},
        {"customer_phone": "call me"},
        {"fulfilment_type": "DELIVERY"},
    ],
)
def test_order_input_is_validated(api_client, shop, override):
    body = {
        "customer_name": "Ada", "customer_phone": "+442079460958", "fulfilment_type": "PICKUP",
        "items": [{"menu_item_id": shop.rice.pk, "quantity": 1}], **override,
    }
    response = api_client.post(
        reverse("public-order-create", kwargs={"slug": shop.restaurant.slug}), body, format="json", HTTP_IDEMPOTENCY_KEY=KEY
    )
    assert response.status_code == 400 and code(response) == "validation_error"
    assert not Order.objects.exists()


@pytest.mark.parametrize("quantity", [0, 100, -1])
def test_quantities_must_be_between_1_and_99(place, shop, quantity):
    assert place(shop.restaurant, [(shop.rice.pk, quantity)]).status_code == 400


def test_an_order_has_a_limited_number_of_lines(place, shop):
    assert place(shop.restaurant, [(i, 1) for i in range(1, 32)]).status_code == 400


def test_phone_numbers_are_normalised(place, shop):
    place(shop.restaurant, [(shop.rice.pk, 1)], phone="+44 (20) 7946-0958")
    assert Order.objects.get().customer_phone == "+442079460958"


# ---------------------------------------------------------------- availability and settings
def test_unorderable_items_are_reported_and_nothing_is_created(place, shop, make_restaurant, make_category, make_item):
    archived = make_item(shop.category, name="Old")
    archived.archive()
    sold_out = make_item(shop.category, name="Sold out", is_available=False)
    hidden_category = make_category(shop.restaurant, name="Hidden", is_active=False)
    in_hidden = make_item(hidden_category, name="In hidden")
    foreign = make_item(make_category(make_restaurant()), name="Elsewhere")

    response = place(
        shop.restaurant,
        [(shop.rice.pk, 1), (archived.pk, 1), (sold_out.pk, 1), (in_hidden.pk, 1), (foreign.pk, 1)],
    )

    assert response.status_code == 409 and code(response) == "item_unavailable"
    problems = {p["id"]: p["reason"] for p in response.json()["error"]["details"]["items"]}
    assert problems == {
        archived.pk: "not_found", sold_out.pk: "unavailable", in_hidden.pk: "not_found", foreign.pk: "not_found",
    }
    assert not Order.objects.exists()


def test_a_closed_restaurant_takes_no_orders(place, shop):
    shop.restaurant.accepting_orders = False
    shop.restaurant.save()
    response = place(shop.restaurant, [(shop.rice.pk, 1)])
    assert response.status_code == 409 and code(response) == "not_accepting_orders"


def test_a_fulfilment_option_the_restaurant_does_not_offer_is_refused(place, shop, make_restaurant, make_category, make_item):
    pickup_only = make_restaurant(accepting_orders=True)
    item = make_item(make_category(pickup_only))
    response = place(pickup_only, [(item.pk, 1)], fulfilment_type="DINE_IN")
    assert response.status_code == 409 and code(response) == "fulfilment_disabled"


def test_table_numbers_follow_the_restaurants_rules(place, shop):
    shop.restaurant.requires_table_number = True
    shop.restaurant.save()
    missing = place(shop.restaurant, [(shop.rice.pk, 1)], fulfilment_type="DINE_IN")
    assert missing.status_code == 400 and "table_number" in missing.json()["error"]["details"]

    place(shop.restaurant, [(shop.rice.pk, 1)], fulfilment_type="DINE_IN", table_number="12")
    place(shop.restaurant, [(shop.rice.pk, 1)], fulfilment_type="PICKUP", table_number="5", phone="+442079460001")
    assert sorted(Order.objects.values_list("table_number", flat=True), key=str) == ["12", None]


def test_unknown_and_suspended_restaurants_are_404(api_client, place, shop):
    shop.restaurant.is_active = False
    shop.restaurant.save()
    assert place(shop.restaurant, [(shop.rice.pk, 1)]).status_code == 404
    unknown = type("R", (), {"slug": "does-not-exist"})
    assert place(unknown, [(shop.rice.pk, 1)]).status_code == 404


def test_order_codes_restart_per_restaurant(place, shop, make_restaurant, make_category, make_item):
    other = make_restaurant(accepting_orders=True)
    other_item = make_item(make_category(other))
    codes = [
        place(shop.restaurant, [(shop.rice.pk, 1)], phone="+442079460001").json()["code"],
        place(shop.restaurant, [(shop.rice.pk, 1)], phone="+442079460002").json()["code"],
        place(other, [(other_item.pk, 1)]).json()["code"],
    ]
    assert codes == ["001", "002", "001"]


def test_a_phone_number_cannot_pile_up_pending_orders(place, shop):
    for _ in range(3):
        assert place(shop.restaurant, [(shop.rice.pk, 1)]).status_code == 201
    response = place(shop.restaurant, [(shop.rice.pk, 1)])
    assert response.status_code == 409 and code(response) == "too_many_open_orders"


def test_order_creation_is_rate_limited(place, shop):
    for _ in range(30):
        place(shop.restaurant, [])
    assert place(shop.restaurant, []).status_code == 429


# ---------------------------------------------------------------- idempotency
def test_the_idempotency_key_is_required(api_client, shop):
    url = reverse("public-order-create", kwargs={"slug": shop.restaurant.slug})
    body = {"customer_name": "Ada", "customer_phone": "+442079460958", "fulfilment_type": "PICKUP",
            "items": [{"menu_item_id": shop.rice.pk, "quantity": 1}]}
    assert code(api_client.post(url, body, format="json")) == "idempotency_key_required"
    assert api_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="short").status_code == 400
    assert not Order.objects.exists()


def test_a_retry_returns_the_same_order_instead_of_creating_another(place, shop):
    first = place(shop.restaurant, [(shop.rice.pk, 2)], key=KEY)
    retry = place(shop.restaurant, [(shop.rice.pk, 2)], key=KEY)
    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json()
    assert retry.headers["Idempotent-Replay"] == "true"
    assert Order.objects.count() == 1


def test_a_retry_still_succeeds_after_the_restaurant_closed(place, shop):
    first = place(shop.restaurant, [(shop.rice.pk, 1)], key=KEY)
    shop.restaurant.accepting_orders = False
    shop.restaurant.save()
    assert place(shop.restaurant, [(shop.rice.pk, 1)], key=KEY).json() == first.json()


def test_reusing_a_key_for_a_different_order_is_refused(place, shop):
    place(shop.restaurant, [(shop.rice.pk, 1)], key=KEY)
    response = place(shop.restaurant, [(shop.rice.pk, 2)], key=KEY)
    assert response.status_code == 409 and code(response) == "idempotency_key_reused"
    assert Order.objects.count() == 1


def test_the_same_key_in_another_restaurant_is_independent(place, shop, make_restaurant, make_category, make_item):
    other = make_restaurant(accepting_orders=True)
    other_item = make_item(make_category(other))
    place(shop.restaurant, [(shop.rice.pk, 1)], key=KEY)
    assert place(other, [(other_item.pk, 1)], key=KEY).status_code == 201


# ---------------------------------------------------------------- looking up and cancelling
def test_lookup_shows_status_but_not_who_ordered(place, shop, api_client):
    token = place(shop.restaurant, [(shop.rice.pk, 2)], notes="No salt").json()["token"]
    response = lookup(api_client, token)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store" and response.headers["Referrer-Policy"] == "no-referrer"
    body = response.json()
    assert set(body) == {
        "code", "status", "payment_status", "fulfilment_type", "table_number", "currency", "subtotal", "total",
        "restaurant", "items", "timeline", "cancellable", "created_at", "updated_at",
    }
    assert body["restaurant"] == {"slug": shop.restaurant.slug, "name": shop.restaurant.name}
    assert "Ada" not in str(body) and "442079460958" not in str(body) and "No salt" not in str(body)


def test_bad_tokens_all_get_the_same_404(place, shop, api_client):
    token = place(shop.restaurant, [(shop.rice.pk, 1)]).json()["token"]
    flipped = token[:-1] + ("0" if token[-1] != "0" else "1")
    bad = [flipped, "0" * 96, token[:32] + "0" * 64, token.upper(), token[:-1], token + "0", "short", "x" * 96]
    responses = [lookup(api_client, t) for t in bad]
    assert {r.status_code for r in responses} == {404}
    assert len({str(r.json()) for r in responses}) == 1
    assert lookup(api_client, token).status_code == 200


def test_raising_token_version_revokes_the_link(place, shop, api_client):
    token = place(shop.restaurant, [(shop.rice.pk, 1)]).json()["token"]
    Order.objects.update(token_version=2)
    assert lookup(api_client, token).status_code == 404


def test_a_token_only_opens_its_own_order(place, shop, api_client):
    first = place(shop.restaurant, [(shop.rice.pk, 1)], phone="+442079460001").json()
    second = place(shop.restaurant, [(shop.rice.pk, 1)], phone="+442079460002").json()
    assert lookup(api_client, first["token"]).json()["code"] == "001"
    assert lookup(api_client, second["token"]).json()["code"] == "002"


def test_lookup_is_rate_limited(api_client):
    for _ in range(600):
        lookup(api_client, "0" * 96)
    assert lookup(api_client, "0" * 96).status_code == 429


def test_a_customer_can_cancel_while_pending(place, shop, api_client):
    token = place(shop.restaurant, [(shop.rice.pk, 1)]).json()["token"]
    response = api_client.post(reverse("public-order-cancel", kwargs={"token": token}))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED" and body["cancellable"] is False
    event = OrderStatusEvent.objects.latest("id")
    assert (event.from_status, event.to_status, event.actor_type, event.actor_user) == ("PENDING", "CANCELLED", "CUSTOMER", None)
    again = api_client.post(reverse("public-order-cancel", kwargs={"token": token}))
    assert again.status_code == 409 and code(again) == "invalid_transition"


def test_a_customer_cannot_cancel_once_confirmed(place, shop, api_client):
    token = place(shop.restaurant, [(shop.rice.pk, 1)]).json()["token"]
    Order.objects.update(status="CONFIRMED")
    response = api_client.post(reverse("public-order-cancel", kwargs={"token": token}))
    assert response.status_code == 409 and code(response) == "invalid_transition"
    assert Order.objects.get().status == "CONFIRMED"


def test_cancelling_with_a_bad_token_is_404(api_client):
    assert api_client.post(reverse("public-order-cancel", kwargs={"token": "0" * 96})).status_code == 404
