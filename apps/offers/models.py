"""
Offers and promotions models for Tinashe Takeaway.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Offer(models.Model):
    """Promotional offer that can be applied to orders."""
    
    class OfferType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage Off"
        FIXED = "fixed", "Fixed Amount Off"
        FREE_ITEM = "free_item", "Free Item"
        BUNDLE = "bundle", "Bundle Deal"
    
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
    hero_image = models.ImageField(upload_to="offers/hero/", blank=True)
    display_on_hero = models.BooleanField(
        default=False,
        help_text="Show this offer on the homepage hero banner"
    )
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
    
    def calculate_discount(self, order_subtotal):
        """Calculate discount amount for given subtotal."""
        if not self.is_valid():
            return Decimal("0.00")
        
        if order_subtotal < self.minimum_order_amount:
            return Decimal("0.00")
        
        if self.offer_type == self.OfferType.PERCENTAGE:
            discount = (order_subtotal * self.value) / 100
            return discount.quantize(Decimal("0.01"))
        
        elif self.offer_type == self.OfferType.FIXED:
            return min(self.value, order_subtotal).quantize(Decimal("0.01"))
        
        return Decimal("0.00")
    
    def increment_usage(self):
        """Increment usage count."""
        self.usage_count += 1
        self.save(update_fields=["usage_count"])


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
    
    def is_valid(self, user=None):
        """Check if voucher is currently valid."""
        now = timezone.now()
        
        if not self.is_active or not self.offer.is_active:
            return False
        
        if now < self.valid_from or now > self.valid_until:
            return False
        
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False
        
        # Check per-customer limit
        if user and user.is_authenticated and self.max_uses_per_customer > 0:
            user_usage = VoucherUsage.objects.filter(
                voucher=self,
                user=user
            ).count()
            if user_usage >= self.max_uses_per_customer:
                return False
        
        return True
    
    def calculate_discount(self, order_subtotal):
        """Calculate discount using linked offer."""
        return self.offer.calculate_discount(order_subtotal)
    
    def record_usage(self, user=None, order=None):
        """Record that this voucher was used."""
        self.uses_count += 1
        self.save(update_fields=["uses_count"])
        
        if user and user.is_authenticated:
            VoucherUsage.objects.create(
                voucher=self,
                user=user,
                order=order
            )
        
        self.offer.increment_usage()


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
