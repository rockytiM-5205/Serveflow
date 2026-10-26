"""Read-only admin: orders change only through the API so the status rules always apply."""
from django.contrib import admin

from .models import Order, OrderItem, OrderStatusEvent, Payment


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemInline(ReadOnlyMixin, admin.TabularInline):
    model = OrderItem
    extra = 0


class EventInline(ReadOnlyMixin, admin.TabularInline):
    model = OrderStatusEvent
    extra = 0


class PaymentInline(ReadOnlyMixin, admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Order)
class OrderAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("code", "restaurant", "business_date", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "payment_status", "restaurant")
    search_fields = ("order_number", "public_id")
    inlines = [ItemInline, EventInline, PaymentInline]
