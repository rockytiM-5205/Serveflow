from django.contrib import admin

from .models import MenuCategory, MenuItem


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant", "sort_order", "is_active")
    list_filter = ("is_active", "restaurant")
    search_fields = ("name", "restaurant__name")

    def has_delete_permission(self, request, obj=None):
        return False  # hide with is_active=False


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant", "category", "price", "unit_name", "is_available", "archived_at")
    list_filter = ("is_available", "restaurant")
    search_fields = ("name", "restaurant__name")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False  # archive instead; orders keep referring to items
