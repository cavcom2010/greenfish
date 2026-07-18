"""
Config context processors - Site settings in templates.
"""
# Import from core for backward compatibility
# In future: from .models import SiteSettings
from django.conf import settings as django_settings

from apps.core.models import SiteSettings
from apps.core.services.opening_hours import opening_hours_rows


def site_settings(request):
    """Add site settings to template context."""
    settings = SiteSettings.get()
    hours_rows, hours_text = opening_hours_rows(settings.opening_hours)
    return {
        "site_settings": settings,
        "delivery_enabled": settings.is_delivery_enabled,
        "opening_hours_rows": hours_rows,
        "opening_hours_text": hours_text,
        "VAPID_PUBLIC_KEY": getattr(django_settings, "VAPID_PUBLIC_KEY", ""),
    }
