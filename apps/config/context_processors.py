"""
Config context processors - Site settings in templates.
"""
# Import from core for backward compatibility
# In future: from .models import SiteSettings
from apps.core.models import SiteSettings


def site_settings(request):
    """Add site settings to template context."""
    return {
        "site_settings": SiteSettings.get(),
    }
