"""Admin for meal deals."""
from django.contrib import admin

from .models import MealDeal, MealDealItem, MealDealOption


class MealDealItemInline(admin.TabularInline):
    model = MealDealItem
    extra = 1
    ordering = ["sort_order"]


class MealDealOptionInline(admin.TabularInline):
    model = MealDealOption
    extra = 1
    autocomplete_fields = ["menu_item"]


@admin.register(MealDeal)
class MealDealAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "deal_type",
        "deal_price",
        "savings",
        "is_active",
        "sort_order",
    ]
    list_filter = ["deal_type", "is_active"]
    list_editable = ["sort_order", "is_active"]
    search_fields = ["name", "description"]
    inlines = [MealDealItemInline]


@admin.register(MealDealItem)
class MealDealItemAdmin(admin.ModelAdmin):
    list_display = ["deal", "name", "min_quantity", "max_quantity", "sort_order"]
    list_filter = ["deal"]
    inlines = [MealDealOptionInline]
    ordering = ["deal", "sort_order"]


@admin.register(MealDealOption)
class MealDealOptionAdmin(admin.ModelAdmin):
    list_display = ["deal_item", "menu_item", "upgrade_price", "is_available"]
    list_filter = ["deal_item__deal", "is_available"]
    autocomplete_fields = ["menu_item"]
