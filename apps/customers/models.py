"""
Customer models - Business-specific customer data.

This module contains customer profiles, addresses, preferences,
and any business logic related to customers.
"""
from django.conf import settings
from django.db import models


class CustomerProfile(models.Model):
    """
    Extended profile for customers.
    
    This is business-specific customer data that extends the
    authentication.User model. Use this for preferences, loyalty,
    favorites, etc.
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    
    # Preferences
    favorite_items = models.ManyToManyField(
        "menu.MenuItem",
        blank=True,
        related_name="favorited_by"
    )
    notifications_enabled = models.BooleanField(default=True)
    marketing_consent = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "customers_profile"
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"
    
    def __str__(self):
        return f"Profile for {self.user.email}"


class Address(models.Model):
    """Customer address for delivery or billing."""
    
    ADDRESS_TYPES = [
        ('delivery', 'Delivery'),
        ('billing', 'Billing'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses"
    )
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPES, default='delivery')
    name = models.CharField(max_length=100, help_text="E.g., 'Home' or 'Work'")
    street_address = models.CharField(max_length=255)
    apartment = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100)
    postcode = models.CharField(max_length=20)
    phone = models.CharField(max_length=30, blank=True)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "customers_address"
        verbose_name = "Address"
        verbose_name_plural = "Addresses"
    
    def __str__(self):
        return f"{self.name} - {self.street_address}"
