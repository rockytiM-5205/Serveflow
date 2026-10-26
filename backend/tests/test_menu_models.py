"""Menu model constraints. Need PostgreSQL and the menu migrations (0001 and 0002)."""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.menu.models import MenuItem

pytestmark = pytest.mark.django_db


def test_category_names_are_unique_per_restaurant_ignoring_case(make_restaurant, make_category):
    a, b = make_restaurant(), make_restaurant()
    make_category(a, name="Mains")
    make_category(b, name="Mains")  # another restaurant may reuse the name
    with pytest.raises(IntegrityError), transaction.atomic():
        make_category(a, name="mains")


def test_active_item_names_are_unique_per_restaurant_but_archived_ones_free_the_name(
    make_restaurant, make_category, make_item
):
    restaurant = make_restaurant()
    category = make_category(restaurant)
    first = make_item(category, name="Rice")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_item(category, name="rice")
    first.archive()
    make_item(category, name="Rice")


def test_price_cannot_be_negative(make_restaurant, make_category, make_item):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_item(make_category(make_restaurant()), price="-1.00")


def test_price_keeps_two_decimals_without_float_error(make_restaurant, make_category, make_item):
    item = make_item(make_category(make_restaurant()), price="0.10")
    item.refresh_from_db()
    assert str(item.price) == "0.10"


@pytest.mark.parametrize("url", ["http://example.com/a.jpg", "ftp://example.com/a.jpg", "https://a b.jpg", "javascript:alert(1)"])
def test_database_only_accepts_https_image_urls(make_restaurant, make_category, make_item, url):
    category = make_category(make_restaurant())
    with pytest.raises(IntegrityError), transaction.atomic():
        MenuItem.objects.bulk_create([MenuItem(restaurant=category.restaurant, category=category, name="X", price="1", image_url=url)])


def test_empty_image_url_is_stored_as_null(make_restaurant, make_category, make_item):
    item = make_item(make_category(make_restaurant()), image_url="")
    item.refresh_from_db()
    assert item.image_url is None


def test_https_image_url_is_accepted(make_restaurant, make_category, make_item):
    item = make_item(make_category(make_restaurant()), image_url="https://cdn.example.com/rice.jpg")
    assert item.image_url == "https://cdn.example.com/rice.jpg"


def test_database_rejects_an_item_whose_category_belongs_to_another_restaurant(
    make_restaurant, make_category
):
    a, b = make_restaurant(), make_restaurant()
    category = make_category(a)
    with pytest.raises(IntegrityError), transaction.atomic():
        MenuItem.objects.create(restaurant=b, category=category, name="Stray", price="1.00")


def test_full_clean_reports_a_cross_restaurant_category(make_restaurant, make_category):
    a, b = make_restaurant(), make_restaurant()
    item = MenuItem(restaurant=b, category=make_category(a), name="Stray", price="1.00")
    with pytest.raises(ValidationError) as exc:
        item.full_clean()
    assert "category" in exc.value.message_dict
