"""
Admin configuration for the menu app.
"""
from django.contrib import admin

from .models import MenuCategory, MenuItem, MenuModifier


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "sort_order", "is_active", "item_count"]
    list_editable = ["sort_order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)} if hasattr(MenuCategory, 'slug') else {}
    
    def item_count(self, obj):
        return obj.items.filter(is_available=True).count()
    item_count.short_description = "Available Items"


@admin.register(MenuModifier)
class MenuModifierAdmin(admin.ModelAdmin):
    list_display = ["name", "price_adjustment", "is_active"]
    list_editable = ["price_adjustment", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


class MenuItemModifierInline(admin.TabularInline):
    model = MenuItem.modifiers.through
    extra = 1


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "category",
        "price",
        "is_available",
        "is_popular",
        "preparation_time",
        "sort_order"
    ]
    list_editable = ["price", "is_available", "is_popular", "sort_order"]
    list_filter = ["category", "is_available", "is_popular", "dietary_tags"]
    search_fields = ["name", "description"]
    filter_horizontal = ["modifiers"]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("category", "name", "description", "price", "image")
        }),
        ("Availability", {
            "fields": ("is_available", "is_popular", "preparation_time")
        }),
        ("Details", {
            "fields": ("dietary_tags", "sort_order")
        }),
    )
