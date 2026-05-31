"""
Core models for Tinashe Takeaway.
"""
from django.conf import settings as django_settings
from django.db import models

from .media import (
    FAVICON_IMAGE_VALIDATORS,
    LOGO_IMAGE_VALIDATORS,
    get_changed_image_names,
    sync_instance_image_variants,
    validate_changed_image_fields,
)


SITE_SETTINGS_IMAGE_VARIANTS = {
    "logo": ("logo",),
    "favicon": ("favicon",),
}


class SiteSettings(models.Model):
    """Global site settings for the takeaway shop."""
    
    shop_name = models.CharField(max_length=100, default="My Restaurant")
    address = models.TextField(default="123 High Street, Harare")
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    
    # Opening hours stored as JSON: {"0": {"open": "09:00", "close": "22:00"}, ...}
    # 0=Monday, 6=Sunday
    opening_hours = models.JSONField(default=dict, blank=True)
    
    currency = models.CharField(max_length=3, default="GBP")
    delivery_enabled = models.BooleanField(
        default=True,
        help_text="Allow customers to choose delivery when the DELIVERY_ENABLED environment switch is also on.",
    )
    logo = models.ImageField(upload_to="site/", blank=True, validators=LOGO_IMAGE_VALIDATORS)
    favicon = models.ImageField(upload_to="site/", blank=True, validators=FAVICON_IMAGE_VALIDATORS)
    theme_color = models.CharField(max_length=7, default="#FF6B35", help_text="Hex color code for PWA theme")
    
    # Social links
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"
    
    def __str__(self):
        return self.shop_name

    @property
    def is_delivery_enabled(self):
        """Return whether delivery is available after env and admin controls."""
        return bool(getattr(django_settings, "DELIVERY_ENABLED", True) and self.delivery_enabled)
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SiteSettings.objects.exists():
            raise ValueError("Only one SiteSettings instance allowed")
        changed_images = get_changed_image_names(self, SITE_SETTINGS_IMAGE_VARIANTS.keys())
        validate_changed_image_fields(self, changed_images)
        super().save(*args, **kwargs)
        sync_instance_image_variants(self, SITE_SETTINGS_IMAGE_VARIANTS, changed_images)
    
    @classmethod
    def get(cls):
        """Get or create the singleton site settings."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
