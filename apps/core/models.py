"""
Core models for Tinashe Takeaway.
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
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
    delivery_map_enabled = models.BooleanField(
        default=True,
        help_text="Use Google Maps address search and delivery-zone validation when API keys and shop coordinates are configured.",
    )
    delivery_minimum_order_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal("15.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Minimum food subtotal for delivery orders. Leave blank to use DELIVERY_MINIMUM_ORDER_AMOUNT from .env. Use 0 to disable.",
    )
    delivery_default_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default delivery fee used before a distance zone is matched, or when manual address entry is used. Leave blank to use DELIVERY_DEFAULT_FEE from .env.",
    )
    order_personal_data_retention_years = models.PositiveSmallIntegerField(
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Years to keep customer-identifying order details before anonymisation. Business totals and item records are retained.",
    )
    cart_item_quantity_limit = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text="Maximum quantity a customer can self-serve for one basket item. Leave blank to use MAX_CART_ITEM_QUANTITY from .env.",
    )
    shop_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
        help_text="Shop latitude used for delivery maps. Leave blank to use SHOP_LATITUDE from .env.",
    )
    shop_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
        help_text="Shop longitude used for delivery maps. Leave blank to use SHOP_LONGITUDE from .env.",
    )
    delivery_radius_miles = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.00"),
        validators=[MinValueValidator(Decimal("0.10"))],
        help_text="Maximum delivery distance from the shop in miles.",
    )
    logo = models.ImageField(upload_to="site/", blank=True, validators=LOGO_IMAGE_VALIDATORS)
    favicon = models.ImageField(upload_to="site/", blank=True, validators=FAVICON_IMAGE_VALIDATORS)
    theme_color = models.CharField(max_length=7, default="#FF6B35", help_text="Hex color code for PWA theme")
    homepage_hero_enabled = models.BooleanField(
        default=False,
        help_text="Show the marketing hero banner at the top of the homepage.",
    )
    delivery_eta_text = models.CharField(
        max_length=60,
        blank=True,
        help_text='Delivery time estimate shown on the homepage, e.g. "40–60 min". Blank hides it.',
    )
    
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

    @staticmethod
    def _decimal_from_setting(value):
        try:
            if value in (None, ""):
                return None
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @property
    def shop_coordinates(self):
        """Return shop coordinates from admin settings with env fallback."""
        latitude = self.shop_latitude
        longitude = self.shop_longitude
        if latitude is None:
            latitude = self._decimal_from_setting(getattr(django_settings, "SHOP_LATITUDE", ""))
        if longitude is None:
            longitude = self._decimal_from_setting(getattr(django_settings, "SHOP_LONGITUDE", ""))
        if latitude is None or longitude is None:
            return None
        return (latitude, longitude)

    @property
    def delivery_radius_value(self):
        """Return delivery radius from admin settings with env fallback."""
        if self.delivery_radius_miles:
            return self.delivery_radius_miles
        return self._decimal_from_setting(getattr(django_settings, "DELIVERY_RADIUS_MILES", 3)) or Decimal("3.00")

    @property
    def delivery_minimum_order_amount_value(self):
        """Return delivery minimum spend from admin settings with env fallback."""
        if self.delivery_minimum_order_amount is not None:
            return self.delivery_minimum_order_amount
        return (
            self._decimal_from_setting(getattr(django_settings, "DELIVERY_MINIMUM_ORDER_AMOUNT", "15.00"))
            or Decimal("15.00")
        )

    @property
    def delivery_default_fee_value(self):
        """Return fallback delivery fee from admin settings with env fallback."""
        if self.delivery_default_fee is not None:
            return self.delivery_default_fee.quantize(Decimal("0.01"))
        return (
            self._decimal_from_setting(getattr(django_settings, "DELIVERY_DEFAULT_FEE", "0.00"))
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))

    @property
    def cart_item_quantity_limit_value(self):
        """Return the normal self-service per-item basket cap."""
        if self.cart_item_quantity_limit is not None:
            return max(1, int(self.cart_item_quantity_limit))
        try:
            return max(1, int(getattr(django_settings, "MAX_CART_ITEM_QUANTITY", 20)))
        except (TypeError, ValueError):
            return 20

    @property
    def is_delivery_map_configured(self):
        """Return whether Google Maps delivery-zone UX can be used."""
        return bool(
            self.is_delivery_enabled
            and self.delivery_map_enabled
            and getattr(django_settings, "GOOGLE_MAPS_API_KEY", "")
            and self.shop_coordinates
        )
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SiteSettings.objects.exists():
            raise ValueError("Only one SiteSettings instance allowed")
        changed_images = get_changed_image_names(self, SITE_SETTINGS_IMAGE_VARIANTS.keys())
        validate_changed_image_fields(self, changed_images)
        super().save(*args, **kwargs)
        sync_instance_image_variants(self, SITE_SETTINGS_IMAGE_VARIANTS, changed_images)
        cache.delete(self.CACHE_KEY)

    CACHE_KEY = "core:site-settings:v1"
    CACHE_TTL_SECONDS = 60

    @classmethod
    def get(cls):
        """Get the singleton site settings, cached briefly to avoid a DB hit
        on every request/template render. Saving invalidates the cache."""
        cached = cache.get(cls.CACHE_KEY)
        if cached is not None:
            return cached
        settings, _ = cls.objects.get_or_create(pk=1)
        try:
            cache.set(cls.CACHE_KEY, settings, timeout=cls.CACHE_TTL_SECONDS)
        except Exception:
            pass
        return settings


class TimeStampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class NotificationEvent(TimeStampedModel):
    """Durable outbox entry for customer/staff notifications."""

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        PUSH = "push", "Push"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    channel = models.CharField(max_length=20, choices=Channel.choices, db_index=True)
    event_type = models.CharField(max_length=80, db_index=True)
    recipient = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_events",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["next_attempt_at", "created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.channel}:{self.event_type} ({self.status})"


class LargeOrderRequest(TimeStampedModel):
    """Customer request for catering, party, or corporate-size orders."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUOTED = "quoted", "Quoted"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    class ServiceType(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        DELIVERY = "delivery", "Delivery"

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="large_order_requests",
    )
    name = models.CharField(max_length=120)
    company_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30)
    email = models.EmailField()
    event_datetime = models.DateTimeField(null=True, blank=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices, default=ServiceType.PICKUP)
    delivery_address = models.TextField(blank=True)
    postcode = models.CharField(max_length=20, blank=True)
    guest_count = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    requested_items = models.TextField(help_text="Customer notes about requested food, quantities, budget, or event needs.")
    basket_snapshot = models.JSONField(default=dict, blank=True)
    estimated_total = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    staff_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["event_datetime"]),
        ]

    def __str__(self):
        return f"{self.name} large order ({self.get_status_display()})"
