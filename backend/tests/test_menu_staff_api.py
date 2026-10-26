"""Staff menu endpoints: roles, tenant isolation, validation, audit."""
import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.restaurants.models import MembershipRole

pytestmark = pytest.mark.django_db

STAFF, MANAGER, OWNER = MembershipRole.STAFF, MembershipRole.MANAGER, MembershipRole.OWNER


def u(name, slug, **kwargs):
    return reverse(name, kwargs={"slug": slug, **kwargs})


def code(response):
    return response.json()["error"]["code"]


# ---------------------------------------------------------------- roles
def test_staff_can_read_but_not_write_the_menu(api_client, make_restaurant, make_category, staff_login):
    restaurant = make_restaurant()
    category = make_category(restaurant)
    staff_login(restaurant, STAFF)

    assert api_client.get(u("staff-menu-categories", restaurant.slug)).status_code == 200
    assert api_client.get(u("staff-menu-items", restaurant.slug)).status_code == 200
    for response in (
        api_client.post(u("staff-menu-categories", restaurant.slug), {"name": "X"}, format="json"),
        api_client.patch(u("staff-menu-category", restaurant.slug, pk=category.pk), {"name": "Y"}, format="json"),
        api_client.post(
            u("staff-menu-items", restaurant.slug),
            {"category": category.pk, "name": "X", "price": "1.00"}, format="json",
        ),
    ):
        assert response.status_code == 403
        assert code(response) == "insufficient_role"


@pytest.mark.parametrize("role", [STAFF, MANAGER, OWNER])
def test_any_staff_role_can_toggle_availability(api_client, make_restaurant, make_category, make_item, staff_login, role):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant))
    staff_login(restaurant, role)

    response = api_client.patch(
        u("staff-menu-item-availability", restaurant.slug, pk=item.pk), {"is_available": False}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["is_available"] is False
    item.refresh_from_db()
    assert item.is_available is False


def test_staff_cannot_archive_items(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant))
    staff_login(restaurant, STAFF)
    response = api_client.post(u("staff-menu-item-archive", restaurant.slug, pk=item.pk))
    assert response.status_code == 403
    item.refresh_from_db()
    assert item.archived_at is None


def test_anonymous_gets_401_on_every_staff_menu_route(api_client, make_restaurant, make_category, make_item):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant))
    for url in (
        u("staff-menu-categories", restaurant.slug),
        u("staff-menu-items", restaurant.slug),
        u("staff-menu-item", restaurant.slug, pk=item.pk),
        u("staff-audit", restaurant.slug),
    ):
        assert api_client.get(url).status_code == 401


# ---------------------------------------------------------------- tenant isolation
def test_another_restaurants_ids_are_404_on_every_detail_route(
    api_client, make_restaurant, make_category, make_item, staff_login
):
    mine, other = make_restaurant(), make_restaurant()
    staff_login(mine, OWNER)
    foreign_category = make_category(other)
    foreign_item = make_item(foreign_category)

    assert api_client.get(u("staff-menu-category", mine.slug, pk=foreign_category.pk)).status_code == 404
    assert api_client.patch(u("staff-menu-category", mine.slug, pk=foreign_category.pk), {"name": "x"}, format="json").status_code == 404
    assert api_client.get(u("staff-menu-item", mine.slug, pk=foreign_item.pk)).status_code == 404
    assert api_client.patch(u("staff-menu-item", mine.slug, pk=foreign_item.pk), {"price": "9.00"}, format="json").status_code == 404
    assert api_client.post(u("staff-menu-item-archive", mine.slug, pk=foreign_item.pk)).status_code == 404
    assert api_client.patch(u("staff-menu-item-availability", mine.slug, pk=foreign_item.pk), {"is_available": False}, format="json").status_code == 404
    foreign_item.refresh_from_db()
    assert foreign_item.is_available is True and foreign_item.archived_at is None


def test_lists_only_contain_the_callers_restaurant(api_client, make_restaurant, make_category, make_item, staff_login):
    mine, other = make_restaurant(), make_restaurant()
    staff_login(mine, MANAGER)
    make_item(make_category(mine, name="Mine"), name="Mine item")
    make_item(make_category(other, name="Theirs"), name="Their item")

    assert [c["name"] for c in api_client.get(u("staff-menu-categories", mine.slug)).json()] == ["Mine"]
    assert [i["name"] for i in api_client.get(u("staff-menu-items", mine.slug)).json()] == ["Mine item"]


def test_cannot_create_an_item_in_another_restaurants_category(api_client, make_restaurant, make_category, staff_login):
    mine, other = make_restaurant(), make_restaurant()
    staff_login(mine, MANAGER)
    foreign = make_category(other)
    response = api_client.post(
        u("staff-menu-items", mine.slug), {"category": foreign.pk, "name": "Stray", "price": "1.00"}, format="json"
    )
    assert response.status_code == 400
    assert "category" in response.json()["error"]["details"]


# ---------------------------------------------------------------- categories
def test_manager_creates_and_updates_a_category(api_client, make_restaurant, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, MANAGER)
    created = api_client.post(
        u("staff-menu-categories", restaurant.slug), {"name": "Mains", "sort_order": 3}, format="json"
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Mains" and body["sort_order"] == 3 and body["is_active"] is True

    updated = api_client.patch(u("staff-menu-category", restaurant.slug, pk=body["id"]), {"is_active": False}, format="json")
    assert updated.status_code == 200 and updated.json()["is_active"] is False


def test_duplicate_category_name_is_a_validation_error(api_client, make_restaurant, make_category, staff_login):
    restaurant = make_restaurant()
    staff_login(restaurant, MANAGER)
    make_category(restaurant, name="Mains")
    response = api_client.post(u("staff-menu-categories", restaurant.slug), {"name": "mains"}, format="json")
    assert response.status_code == 400
    assert "name" in response.json()["error"]["details"]


# ---------------------------------------------------------------- items
def test_manager_creates_an_item_with_a_decimal_price(api_client, make_restaurant, make_category, staff_login):
    restaurant = make_restaurant()
    category = make_category(restaurant)
    staff_login(restaurant, MANAGER)

    response = api_client.post(
        u("staff-menu-items", restaurant.slug),
        {"category": category.pk, "name": "Rice", "price": "2.50", "unit_name": "spoon",
         "image_url": "https://cdn.example.com/rice.jpg"},
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["price"] == "2.50" and body["unit_name"] == "spoon" and body["archived"] is False
    assert body["image_url"] == "https://cdn.example.com/rice.jpg"


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"price": "-1"}, "price"),
        ({"price": "abc"}, "price"),
        ({"price": "1.234"}, "price"),
        ({"price": "99999999999"}, "price"),
        ({"image_url": "http://example.com/a.jpg"}, "image_url"),
        ({"image_url": "javascript:alert(1)"}, "image_url"),
        ({"name": ""}, "name"),
    ],
)
def test_item_input_is_validated(api_client, make_restaurant, make_category, staff_login, payload, field):
    restaurant = make_restaurant()
    category = make_category(restaurant)
    staff_login(restaurant, MANAGER)
    body = {"category": category.pk, "name": "Rice", "price": "1.00", **payload}
    response = api_client.post(u("staff-menu-items", restaurant.slug), body, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_blank_image_url_is_accepted_and_stored_as_null(api_client, make_restaurant, make_category, staff_login):
    restaurant = make_restaurant()
    category = make_category(restaurant)
    staff_login(restaurant, MANAGER)
    response = api_client.post(
        u("staff-menu-items", restaurant.slug), {"category": category.pk, "name": "Rice", "price": "1", "image_url": ""}, format="json"
    )
    assert response.status_code == 201 and response.json()["image_url"] is None


def test_duplicate_active_item_name_is_rejected(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    category = make_category(restaurant)
    make_item(category, name="Rice")
    staff_login(restaurant, MANAGER)
    response = api_client.post(
        u("staff-menu-items", restaurant.slug), {"category": category.pk, "name": "RICE", "price": "1"}, format="json"
    )
    assert response.status_code == 400 and "name" in response.json()["error"]["details"]


def test_item_list_hides_archived_unless_asked_and_filters_by_category(
    api_client, make_restaurant, make_category, make_item, staff_login
):
    restaurant = make_restaurant()
    first, second = make_category(restaurant), make_category(restaurant)
    make_item(first, name="A")
    make_item(first, name="Old").archive()
    make_item(second, name="B")
    staff_login(restaurant, STAFF)
    url = u("staff-menu-items", restaurant.slug)

    assert [i["name"] for i in api_client.get(url).json()] == ["A", "B"]
    assert [i["name"] for i in api_client.get(url, {"include_archived": "1"}).json()] == ["A", "B", "Old"]
    assert [i["name"] for i in api_client.get(url, {"category": second.pk}).json()] == ["B"]


def test_price_change_is_audited_with_old_and_new_values(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant), name="Rice", price="5.00")
    user = staff_login(restaurant, MANAGER)

    response = api_client.patch(u("staff-menu-item", restaurant.slug, pk=item.pk), {"price": "6.50"}, format="json")

    assert response.status_code == 200 and response.json()["price"] == "6.50"
    entry = AuditLog.objects.get()
    assert (entry.restaurant, entry.actor, entry.action) == (restaurant, user, "menu_item.price_changed")
    assert entry.entity_id == item.pk
    assert entry.metadata == {"item": "Rice", "from": "5.00", "to": "6.50"}


def test_editing_other_fields_does_not_write_an_audit_entry(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant), price="5.00")
    staff_login(restaurant, MANAGER)
    api_client.patch(u("staff-menu-item", restaurant.slug, pk=item.pk), {"description": "Tasty", "price": "5.00"}, format="json")
    assert AuditLog.objects.count() == 0


def test_archiving_hides_the_item_publicly_audits_and_is_repeatable(
    api_client, make_restaurant, make_category, make_item, staff_login
):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant), name="Rice")
    staff_login(restaurant, MANAGER)
    url = u("staff-menu-item-archive", restaurant.slug, pk=item.pk)

    first = api_client.post(url)
    again = api_client.post(url)

    assert first.status_code == again.status_code == 200
    assert first.json()["archived"] is True
    assert AuditLog.objects.filter(action="menu_item.archived").count() == 1
    public = api_client.get(reverse("public-menu", kwargs={"slug": restaurant.slug})).json()
    assert public["categories"] == []


def test_archived_items_cannot_be_edited_or_toggled(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant))
    item.archive()
    staff_login(restaurant, MANAGER)

    edit = api_client.patch(u("staff-menu-item", restaurant.slug, pk=item.pk), {"price": "9.00"}, format="json")
    toggle = api_client.patch(u("staff-menu-item-availability", restaurant.slug, pk=item.pk), {"is_available": False}, format="json")

    assert edit.status_code == toggle.status_code == 409
    assert code(edit) == code(toggle) == "item_archived"


def test_availability_requires_a_boolean(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant))
    staff_login(restaurant, STAFF)
    url = u("staff-menu-item-availability", restaurant.slug, pk=item.pk)
    assert api_client.patch(url, {}, format="json").status_code == 400
    assert api_client.patch(url, {"is_available": "maybe"}, format="json").status_code == 400


def test_put_and_delete_are_not_offered(api_client, make_restaurant, make_category, make_item, staff_login):
    restaurant = make_restaurant()
    item = make_item(make_category(restaurant))
    staff_login(restaurant, OWNER)
    url = u("staff-menu-item", restaurant.slug, pk=item.pk)
    assert api_client.put(url, {}, format="json").status_code == 405
    assert api_client.delete(url).status_code == 405


# ---------------------------------------------------------------- audit endpoint
def test_audit_list_is_manager_only_and_tenant_scoped(api_client, make_restaurant, make_category, make_item, staff_login):
    mine, other = make_restaurant(), make_restaurant()
    own_item = make_item(make_category(mine))
    other_item = make_item(make_category(other))
    staff_user = staff_login(mine, MANAGER)
    api_client.patch(u("staff-menu-item", mine.slug, pk=own_item.pk), {"price": "7.00"}, format="json")
    AuditLog.objects.create(restaurant=other, actor=None, action="menu_item.archived", entity_type="menu_item", entity_id=other_item.pk)

    body = api_client.get(u("staff-audit", mine.slug)).json()

    assert [e["action"] for e in body["results"]] == ["menu_item.price_changed"]
    assert body["results"][0]["actor_email"] == staff_user.email

    staff_login(mine, STAFF)
    assert api_client.get(u("staff-audit", mine.slug)).status_code == 403
