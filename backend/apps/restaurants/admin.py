from django.contrib import admin

from .models import Restaurant, RestaurantMembership


class MembershipInline(admin.TabularInline):
    model = RestaurantMembership
    fields = ("user", "role", "is_active")
    autocomplete_fields = ("user",)
    extra = 0
    can_delete = False  # deactivate instead of deleting


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "accepting_orders", "currency", "timezone")
    list_filter = ("is_active", "accepting_orders")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [MembershipInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "contact_phone", "address")}),
        ("Status", {"fields": ("is_active", "accepting_orders")}),
        ("Regional", {"fields": ("currency", "timezone")}),
        ("Fulfilment", {"fields": ("pickup_enabled", "dine_in_enabled", "requires_table_number")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def has_delete_permission(self, request, obj=None):
        # Restaurants own order history; suspend with is_active=False instead.
        return False


@admin.register(RestaurantMembership)
class RestaurantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "restaurant", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "restaurant__name", "restaurant__slug")
    autocomplete_fields = ("user", "restaurant")

    def has_delete_permission(self, request, obj=None):
        return False
