"""
Admin configuration for the core app.
"""
from django.contrib import admin

from .models import SiteSettings


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
            "fields": ("currency", "delivery_enabled")
        }),
        ("Social Media", {
            "fields": ("facebook_url", "instagram_url", "twitter_url"),
            "classes": ("collapse",)
        }),
    )
