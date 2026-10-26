from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Cursor pagination, 25 per page, up to 100. Subclasses set `ordering`."""

    page_size = 25
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = ("-id",)
