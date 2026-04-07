"""
Admin configuration for the offers app.
"""
from django.contrib import admin

from .models import Offer, VoucherCode, VoucherUsage


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "offer_type",
        "value",
        "minimum_order_amount",
        "is_active",
        "display_on_hero",
        "start_date",
        "end_date",
        "usage_count"
    ]
    list_filter = ["offer_type", "is_active", "display_on_hero", "start_date"]
    search_fields = ["name", "description"]
    filter_horizontal = ["applicable_items", "applicable_categories"]
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "description", "offer_type", "value")
        }),
        ("Conditions", {
            "fields": ("minimum_order_amount", "applicable_items", "applicable_categories")
        }),
        ("Validity", {
            "fields": ("start_date", "end_date", "is_active")
        }),
        ("Display", {
            "fields": ("hero_title", "hero_subtitle", "hero_image", "display_on_hero", "display_order")
        }),
        ("Limits", {
            "fields": ("max_usage_count", "usage_count"),
            "classes": ("collapse",)
        }),
    )


@admin.register(VoucherCode)
class VoucherCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "offer",
        "max_uses",
        "uses_count",
        "is_active",
        "valid_from",
        "valid_until"
    ]
    list_filter = ["is_active", "offer", "valid_from"]
    search_fields = ["code", "offer__name"]
    
    fieldsets = (
        (None, {
            "fields": ("code", "offer")
        }),
        ("Usage Limits", {
            "fields": ("max_uses", "uses_count", "max_uses_per_customer")
        }),
        ("Validity", {
            "fields": ("valid_from", "valid_until", "is_active")
        }),
    )


@admin.register(VoucherUsage)
class VoucherUsageAdmin(admin.ModelAdmin):
    list_display = ["voucher", "user", "order", "used_at"]
    list_filter = ["used_at", "voucher"]
    search_fields = ["voucher__code", "user__email"]
    readonly_fields = ["used_at"]
