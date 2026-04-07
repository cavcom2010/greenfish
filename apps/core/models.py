"""
Core models for Tinashe Takeaway.
"""
from django.db import models


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
    logo = models.ImageField(upload_to="site/", blank=True)
    favicon = models.ImageField(upload_to="site/", blank=True)
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
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SiteSettings.objects.exists():
            raise ValueError("Only one SiteSettings instance allowed")
        super().save(*args, **kwargs)
    
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
