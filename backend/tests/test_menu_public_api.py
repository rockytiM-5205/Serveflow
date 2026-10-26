"""Public restaurant and menu endpoints (no authentication)."""
import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def restaurant_url(slug):
    return reverse("public-restaurant", kwargs={"slug": slug})


def menu_url(slug):
    return reverse("public-menu", kwargs={"slug": slug})


def test_public_restaurant_details(api_client, make_restaurant):
    restaurant = make_restaurant(description="Home cooking", dine_in_enabled=True, requires_table_number=True)
    body = api_client.get(restaurant_url(restaurant.slug)).json()
    assert body["name"] == restaurant.name
    assert body["currency"] == "USD"
    assert body["accepting_orders"] is False
    assert body["dine_in_enabled"] is True and body["requires_table_number"] is True
    assert set(body) == {
        "slug", "name", "description", "contact_phone", "address", "currency", "timezone",
        "accepting_orders", "pickup_enabled", "dine_in_enabled", "requires_table_number",
    }


def test_unknown_and_suspended_restaurants_are_404(api_client, make_restaurant):
    suspended = make_restaurant(is_active=False)
    for slug in ("does-not-exist", suspended.slug):
        for url in (restaurant_url(slug), menu_url(slug)):
            response = api_client.get(url)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"


def test_public_menu_groups_items_by_ordered_category(api_client, make_restaurant, make_category, make_item):
    restaurant = make_restaurant()
    drinks = make_category(restaurant, name="Drinks", sort_order=2)
    mains = make_category(restaurant, name="Mains", sort_order=1)
    make_item(mains, name="Rice", price="2.50", unit_name="spoon")
    make_item(drinks, name="Water", price="1.00", is_available=False)

    body = api_client.get(menu_url(restaurant.slug)).json()

    assert body["restaurant"] == {"slug": restaurant.slug, "name": restaurant.name, "currency": "USD"}
    assert [c["name"] for c in body["categories"]] == ["Mains", "Drinks"]
    rice = body["categories"][0]["items"][0]
    assert rice == {
        "id": rice["id"], "name": "Rice", "description": "", "price": "2.50",
        "unit_name": "spoon", "is_available": True, "image_url": None,
    }
    assert body["categories"][1]["items"][0]["is_available"] is False  # shown, flagged unavailable


def test_public_menu_hides_archived_items_inactive_and_empty_categories(
    api_client, make_restaurant, make_category, make_item
):
    restaurant = make_restaurant()
    shown = make_category(restaurant, name="Shown")
    hidden = make_category(restaurant, name="Hidden", is_active=False)
    make_category(restaurant, name="Empty")
    make_item(shown, name="Visible")
    make_item(shown, name="Gone").archive()
    make_item(hidden, name="In hidden category")

    body = api_client.get(menu_url(restaurant.slug)).json()

    assert [c["name"] for c in body["categories"]] == ["Shown"]
    assert [i["name"] for i in body["categories"][0]["items"]] == ["Visible"]


def test_public_menu_never_leaks_another_restaurants_items(api_client, make_restaurant, make_category, make_item):
    mine, other = make_restaurant(), make_restaurant()
    make_item(make_category(mine), name="Mine")
    make_item(make_category(other), name="Theirs")
    names = [i["name"] for c in api_client.get(menu_url(mine.slug)).json()["categories"] for i in c["items"]]
    assert names == ["Mine"]


def test_public_menu_does_not_expose_internal_fields(api_client, make_restaurant, make_category, make_item):
    restaurant = make_restaurant()
    make_item(make_category(restaurant))
    item = api_client.get(menu_url(restaurant.slug)).json()["categories"][0]["items"][0]
    assert not {"restaurant", "category", "archived_at", "created_at", "updated_at"} & set(item)


def test_menu_query_count_does_not_grow_with_the_menu(
    api_client, make_restaurant, make_category, make_item, django_assert_max_num_queries
):
    restaurant = make_restaurant()
    for _ in range(4):
        category = make_category(restaurant)
        for _ in range(5):
            make_item(category)
    with django_assert_max_num_queries(4):
        assert api_client.get(menu_url(restaurant.slug)).status_code == 200
