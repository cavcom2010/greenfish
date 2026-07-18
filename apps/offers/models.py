"""
Offers and promotions models for Tinashe Takeaway.
"""
import re
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from apps.core.media import (
    MENU_IMAGE_VALIDATORS,
    get_changed_image_names,
    sync_instance_image_variants,
    validate_changed_image_fields,
)


OFFER_IMAGE_VARIANTS = {
    "hero_image": ("hero",),
}


def _normalize_guest_phone(phone):
    """Return a comparable guest phone number."""
    return re.sub(r"\s+", "", (phone or "").strip())


def _normalize_guest_email(email):
    """Return a comparable guest email address."""
    return (email or "").strip().lower()


class Offer(models.Model):
    """Promotional offer that can be applied to orders."""
    
    class OfferType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage Off"
        FIXED = "fixed", "Fixed Amount Off"
        FREE_ITEM = "free_item", "Free Item"
        BUNDLE = "bundle", "Bundle Deal"

    class Audience(models.TextChoices):
        ALL = "all", "All Customers"
        FIRST_ORDER = "first_order", "First Order"
        BIRTHDAY = "birthday", "Birthday"
        OFF_PEAK = "off_peak", "Off-Peak"
    
    name = models.CharField(max_length=100)
    description = models.TextField()
    offer_type = models.CharField(max_length=20, choices=OfferType.choices)
    
    # Value depends on type:
    # - percentage: 20 = 20% off
    # - fixed: 5.00 = £5 off
    # - free_item: item ID to add for free
    value = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    
    # Conditions
    minimum_order_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Minimum order amount to qualify for this offer"
    )
    applicable_items = models.ManyToManyField(
        "menu.MenuItem",
        blank=True,
        related_name="applicable_offers",
        help_text="Leave empty to apply to all items"
    )
    applicable_categories = models.ManyToManyField(
        "menu.MenuCategory",
        blank=True,
        related_name="applicable_offers",
        help_text="Leave empty to apply to all categories"
    )
    
    # Time limits
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # Display
    hero_title = models.CharField(max_length=100, blank=True)
    hero_subtitle = models.CharField(max_length=200, blank=True)
    hero_image = models.ImageField(upload_to="offers/hero/", blank=True, validators=MENU_IMAGE_VALIDATORS)
    display_on_hero = models.BooleanField(
        default=False,
        help_text="Show this offer on the homepage hero banner"
    )
    app_exclusive = models.BooleanField(
        default=False,
        help_text="Show this as a signed-in app/account reward.",
    )
    audience = models.CharField(max_length=20, choices=Audience.choices, default=Audience.ALL)
    badge = models.CharField(max_length=80, blank=True)
    off_peak_start = models.TimeField(null=True, blank=True)
    off_peak_end = models.TimeField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    
    # Tracking
    usage_count = models.PositiveIntegerField(default=0)
    max_usage_count = models.PositiveIntegerField(
        default=0,
        help_text="0 = unlimited"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Offer"
        verbose_name_plural = "Offers"
        ordering = ["display_order", "-created_at"]
    
    def __str__(self):
        return self.name
    
    def is_valid(self):
        """Check if offer is currently valid."""
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.start_date or now > self.end_date:
            return False
        if self.max_usage_count > 0 and self.usage_count >= self.max_usage_count:
            return False
        return True

    def supports_checkout_discount(self):
        """Return whether this offer can be applied directly in checkout."""
        return self.offer_type in {
            self.OfferType.PERCENTAGE,
            self.OfferType.FIXED,
        }

    def is_available_for_user(self, user=None, now=None):
        """Check whether this offer is valid for the current customer context."""
        now = now or timezone.localtime()
        if not self.is_valid():
            return False

        if self.audience == self.Audience.ALL:
            return True

        if self.audience == self.Audience.OFF_PEAK:
            if not self.off_peak_start or not self.off_peak_end:
                return False
            current_time = now.time()
            if self.off_peak_start <= self.off_peak_end:
                return self.off_peak_start <= current_time <= self.off_peak_end
            return current_time >= self.off_peak_start or current_time <= self.off_peak_end

        if not user or not getattr(user, "is_authenticated", False):
            return False

        if self.audience == self.Audience.FIRST_ORDER:
            Order = apps.get_model("orders", "Order")
            return not Order.objects.filter(user=user, payment_status="paid").exists()

        if self.audience == self.Audience.BIRTHDAY:
            profile = getattr(user, "profile", None)
            birthday = getattr(profile, "date_of_birth", None)
            return bool(birthday and birthday.month == now.month and birthday.day == now.day)

        return True
    
    def calculate_discount(self, order_subtotal, *, discount_base=None):
        """Calculate discount amount for given subtotal."""
        if not self.is_valid():
            return Decimal("0.00")
        
        if order_subtotal < self.minimum_order_amount:
            return Decimal("0.00")

        base_amount = Decimal(
            str(order_subtotal if discount_base is None else discount_base)
        ).quantize(Decimal("0.01"))
        base_amount = max(Decimal("0.00"), base_amount)
        
        if self.offer_type == self.OfferType.PERCENTAGE:
            discount = (base_amount * self.value) / 100
            return discount.quantize(Decimal("0.01"))
        
        elif self.offer_type == self.OfferType.FIXED:
            return min(self.value, base_amount).quantize(Decimal("0.01"))
        
        return Decimal("0.00")
    
    def increment_usage(self):
        """Atomically consume one use of this offer, enforcing the usage cap."""
        with transaction.atomic():
            offer = Offer.objects.select_for_update().get(pk=self.pk)
            if offer.max_usage_count > 0 and offer.usage_count >= offer.max_usage_count:
                raise ValidationError("This offer is no longer available.")
            Offer.objects.filter(pk=self.pk).update(usage_count=F("usage_count") + 1)
        self.refresh_from_db(fields=["usage_count"])

    def save(self, *args, **kwargs):
        changed_images = get_changed_image_names(self, OFFER_IMAGE_VARIANTS.keys())
        validate_changed_image_fields(self, changed_images)
        super().save(*args, **kwargs)
        sync_instance_image_variants(self, OFFER_IMAGE_VARIANTS, changed_images)


class VoucherCode(models.Model):
    """Voucher/discount code that customers can enter at checkout."""
    
    code = models.CharField(max_length=20, unique=True, db_index=True)
    offer = models.ForeignKey(
        Offer,
        on_delete=models.CASCADE,
        related_name="voucher_codes"
    )
    
    # Usage limits
    max_uses = models.PositiveIntegerField(
        default=0,
        help_text="0 = unlimited uses"
    )
    uses_count = models.PositiveIntegerField(default=0)
    max_uses_per_customer = models.PositiveIntegerField(
        default=1,
        help_text="0 = unlimited per customer"
    )
    
    # Validity period
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Voucher Code"
        verbose_name_plural = "Voucher Codes"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.code} ({self.offer.name})"
    
    def _guest_usage_count(self, *, guest_phone="", guest_email=""):
        """Return how many matching guest orders already used this voucher."""
        phone = _normalize_guest_phone(guest_phone)
        email = _normalize_guest_email(guest_email)
        if not phone and not email:
            return 0

        Order = apps.get_model("orders", "Order")
        lookup = {"voucher_code__iexact": self.code}
        if phone:
            lookup["customer_phone"] = phone
        else:
            lookup["customer_email__iexact"] = email
        return Order.objects.filter(**lookup).count()

    def is_valid(self, user=None, *, guest_phone="", guest_email=""):
        """Check if voucher is currently valid."""
        now = timezone.now()
        
        if not self.is_active:
            return False

        if not self.offer.is_valid() or not self.offer.supports_checkout_discount():
            return False
        
        if now < self.valid_from or now > self.valid_until:
            return False
        
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False
        
        # Check per-customer limit
        if self.max_uses_per_customer > 0:
            if user and user.is_authenticated:
                user_usage = VoucherUsage.objects.filter(
                    voucher=self,
                    user=user
                ).count()
                if user_usage >= self.max_uses_per_customer:
                    return False
            elif (
                self._guest_usage_count(
                    guest_phone=guest_phone,
                    guest_email=guest_email,
                )
                >= self.max_uses_per_customer
            ):
                return False
        
        return True
    
    def calculate_discount(self, order_subtotal):
        """Calculate discount using linked offer."""
        return self.offer.calculate_discount(order_subtotal)
    
    def record_usage(self, user=None, order=None):
        """Atomically consume one use of this voucher, re-checking limits under lock.

        Raises ValidationError when a concurrent checkout has exhausted the
        voucher, which rolls back the caller's order-creation transaction.
        """
        with transaction.atomic():
            voucher = VoucherCode.objects.select_for_update().get(pk=self.pk)

            if voucher.max_uses > 0 and voucher.uses_count >= voucher.max_uses:
                raise ValidationError("This voucher has just reached its usage limit.")

            if voucher.max_uses_per_customer > 0:
                if user and user.is_authenticated:
                    used = VoucherUsage.objects.filter(voucher=voucher, user=user).count()
                    if used >= voucher.max_uses_per_customer:
                        raise ValidationError("You have already used this voucher.")
                elif order is not None:
                    # The current order already carries this voucher code, so a
                    # count above the limit means another guest order got there first.
                    guest_uses = voucher._guest_usage_count(
                        guest_phone=order.customer_phone,
                        guest_email=order.customer_email,
                    )
                    if guest_uses > voucher.max_uses_per_customer:
                        raise ValidationError("This voucher has already been used.")

            VoucherCode.objects.filter(pk=self.pk).update(uses_count=F("uses_count") + 1)

            if user and user.is_authenticated:
                VoucherUsage.objects.create(
                    voucher=voucher,
                    user=user,
                    order=order
                )

            self.offer.increment_usage()
        self.refresh_from_db(fields=["uses_count"])


class VoucherUsage(models.Model):
    """Track voucher code usage per customer."""
    
    voucher = models.ForeignKey(
        VoucherCode,
        on_delete=models.CASCADE,
        related_name="usages"
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="voucher_usages"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    used_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Voucher Usage"
        verbose_name_plural = "Voucher Usages"
        unique_together = ["voucher", "user", "order"]
    
    def __str__(self):
        return f"{self.voucher.code} used by {self.user.email}"
