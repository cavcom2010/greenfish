"""
Config context processors - Site settings in templates.
"""
# Import from core for backward compatibility
# In future: from .models import SiteSettings
from apps.core.models import SiteSettings


def site_settings(request):
    """Add site settings to template context."""
    settings = SiteSettings.get()
    return {
        "site_settings": settings,
        "delivery_enabled": settings.is_delivery_enabled,
    }
