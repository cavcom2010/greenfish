"""
Config models - Site-wide business configuration.

NOTE: SiteSettings is currently in apps.core for backward compatibility.
In a clean installation, it would be here:

    class SiteSettings(models.Model):
        shop_name = models.CharField(max_length=100)
        address = models.TextField()
        ...

This app is kept as a placeholder for future configuration models
that don't fit in other apps.
"""

# SiteSettings imported from apps.core for backward compatibility
# from apps.core.models import SiteSettings
