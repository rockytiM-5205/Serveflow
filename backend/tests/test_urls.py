"""Guards against routes shadowing each other (a public and a staff view on the same address)."""
from django.urls import get_resolver, resolve
from django.urls.resolvers import URLPattern, URLResolver


def all_routes(patterns=None, prefix=""):
    for entry in patterns if patterns is not None else get_resolver().url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from all_routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern):
            yield route, entry


def test_no_two_api_routes_share_an_address():
    seen, clashes = {}, []
    for route, entry in all_routes():
        if not route.startswith("api/"):
            continue
        # <slug:slug> and <str:token> etc. only matter by position, so compare the shape.
        shape = "/".join("<>" if part.startswith("<") else part for part in route.split("/"))
        if shape in seen:
            clashes.append((route, seen[shape]))
        seen[shape] = route
    assert not clashes, f"these routes shadow each other: {clashes}"


def test_staff_can_reach_the_order_list_and_customers_the_checkout():
    assert resolve("/api/v1/restaurants/green-bowl/orders/").view_name == "staff-orders"
    assert resolve("/api/v1/restaurants/green-bowl/checkout/").view_name == "public-order-create"
    assert resolve("/api/v1/restaurants/green-bowl/menu/").view_name == "public-menu"
    assert resolve("/api/v1/restaurants/green-bowl/menu/categories/").view_name == "staff-menu-categories"
