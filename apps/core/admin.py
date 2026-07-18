"""
Admin configuration for the core app.
"""
from django.contrib import admin

from .models import LargeOrderRequest, NotificationEvent, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ["shop_name", "phone", "email", "updated_at"]
    
    fieldsets = (
        ("Shop Information", {
            "fields": ("shop_name", "address", "phone", "email", "logo", "favicon")
        }),
        ("Business Hours", {
            "fields": ("opening_hours",),
            "description": "Format: {\"0\": {\"open\": \"09:00\", \"close\": \"22:00\"}} where 0=Monday"
        }),
        ("Settings", {
            "fields": (
                "currency",
                "homepage_hero_enabled",
                "delivery_enabled",
                "delivery_minimum_order_amount",
                "delivery_default_fee",
                "delivery_eta_text",
                "cart_item_quantity_limit",
                "order_personal_data_retention_years",
            )
        }),
        ("Delivery Map", {
            "fields": (
                "delivery_map_enabled",
                "shop_latitude",
                "shop_longitude",
                "delivery_radius_miles",
            ),
            "description": "Configure Google Maps delivery-zone checks. Coordinates can also come from .env as SHOP_LATITUDE and SHOP_LONGITUDE.",
        }),
        ("Social Media", {
            "fields": ("facebook_url", "instagram_url", "twitter_url"),
            "classes": ("collapse",)
        }),
    )


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    list_display = ["channel", "event_type", "recipient", "order", "status", "attempts", "next_attempt_at", "created_at"]
    list_filter = ["channel", "event_type", "status", "created_at"]
    search_fields = ["recipient", "order__order_number", "last_error"]
    readonly_fields = ["created_at", "updated_at", "sent_at"]
    actions = ["retry_events"]

    def retry_events(self, request, queryset):
        from django.utils import timezone

        queryset.update(status=NotificationEvent.Status.PENDING, next_attempt_at=timezone.now())

    retry_events.short_description = "Retry selected notification events"


@admin.register(LargeOrderRequest)
class LargeOrderRequestAdmin(admin.ModelAdmin):
    list_display = ["name", "company_name", "phone", "service_type", "guest_count", "event_datetime", "status", "created_at"]
    list_filter = ["status", "service_type", "event_datetime", "created_at"]
    search_fields = ["name", "company_name", "phone", "email", "requested_items", "staff_notes"]
    readonly_fields = ["user", "basket_snapshot", "estimated_total", "created_at", "updated_at"]
    fieldsets = (
        ("Customer", {
            "fields": ("user", "name", "company_name", "phone", "email")
        }),
        ("Request", {
            "fields": (
                "event_datetime",
                "service_type",
                "delivery_address",
                "postcode",
                "guest_count",
                "requested_items",
                "estimated_total",
                "basket_snapshot",
            )
        }),
        ("Staff Handling", {
            "fields": ("status", "staff_notes")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
