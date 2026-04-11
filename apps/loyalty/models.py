"""
Loyalty points system for Tinashe Takeaway.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.media import (
    MENU_IMAGE_VALIDATORS,
    get_changed_image_names,
    sync_instance_image_variants,
    validate_changed_image_fields,
)


LOYALTY_REWARD_IMAGE_VARIANTS = {
    "image": ("card",),
}


class LoyaltySettings(models.Model):
    """Global loyalty program settings."""
    
    points_per_pound = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Points earned per £1 spent"
    )
    points_value = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal("0.01"),
        help_text="£ value of 1 point (e.g., 0.01 = 1p)"
    )
    min_points_redeem = models.PositiveIntegerField(
        default=100,
        help_text="Minimum points required to redeem"
    )
    max_discount_percent = models.PositiveIntegerField(
        default=50,
        help_text="Maximum % of order that can be paid with points"
    )
    welcome_bonus = models.PositiveIntegerField(
        default=50,
        help_text="Points given to new customers"
    )
    birthday_bonus = models.PositiveIntegerField(
        default=100,
        help_text="Points given on customer's birthday"
    )
    
    # Enable/disable features
    enabled = models.BooleanField(default=True)
    enable_referral = models.BooleanField(default=True)
    referral_points = models.PositiveIntegerField(
        default=100,
        help_text="Points for referrer when referee makes first order"
    )
    
    class Meta:
        verbose_name = "Loyalty Settings"
        verbose_name_plural = "Loyalty Settings"
    
    def __str__(self):
        return "Loyalty Program Settings"
    
    @classmethod
    def get(cls):
        """Get or create singleton settings."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


class LoyaltyTransaction(models.Model):
    """Record of points earned or spent."""
    
    class TransactionType(models.TextChoices):
        EARNED = "earned", "Points Earned"
        REDEEMED = "redeemed", "Points Redeemed"
        BONUS = "bonus", "Bonus Points"
        REFERRAL = "referral", "Referral Bonus"
        BIRTHDAY = "birthday", "Birthday Bonus"
        EXPIRED = "expired", "Points Expired"
        ADJUSTMENT = "adjustment", "Manual Adjustment"
    
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="loyalty_transactions"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_transactions"
    )
    
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices
    )
    points = models.IntegerField()  # Positive for earned, negative for redeemed
    
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Loyalty Transaction"
        verbose_name_plural = "Loyalty Transactions"
    
    def __str__(self):
        return f"{self.user.email}: {self.points:+d} points ({self.transaction_type})"


class ReferralCode(models.Model):
    """Referral code for customers to share."""
    
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="referral_code"
    )
    code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Track successful referrals
    successful_referrals = models.PositiveIntegerField(default=0)
    total_points_earned = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Referral Code"
        verbose_name_plural = "Referral Codes"
    
    def __str__(self):
        return f"{self.code} ({self.user.email})"
    
    def record_referral(self, new_user):
        """Record a successful referral."""
        settings = LoyaltySettings.get()
        if not settings.enable_referral:
            return
        
        # Create transaction for referrer
        LoyaltyTransaction.objects.create(
            user=self.user,
            transaction_type=LoyaltyTransaction.TransactionType.REFERRAL,
            points=settings.referral_points,
            description=f"Referral bonus for {new_user.email}"
        )
        
        self.successful_referrals += 1
        self.total_points_earned += settings.referral_points
        self.save()


class PointsRedemption(models.Model):
    """Record of points being redeemed for discounts."""
    
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="points_redemptions"
    )
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="points_redemption"
    )
    
    points_used = models.PositiveIntegerField()
    discount_amount = models.DecimalField(max_digits=6, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Points Redemption"
        verbose_name_plural = "Points Redemptions"
    
    def __str__(self):
        return f"{self.user.email}: {self.points_used} points = £{self.discount_amount}"


class LoyaltyReward(models.Model):
    """Predefined rewards customers can redeem points for."""
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    points_required = models.PositiveIntegerField()
    
    # Reward type
    reward_type = models.CharField(
        max_length=20,
        choices=[
            ("discount_fixed", "Fixed Discount (£)"),
            ("discount_percent", "Percentage Discount (%)"),
            ("free_item", "Free Menu Item"),
        ],
        default="discount_fixed"
    )
    
    # Value depends on type
    discount_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00")
    )
    free_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to="loyalty/rewards/", blank=True, validators=MENU_IMAGE_VALIDATORS)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["points_required"]
        verbose_name = "Loyalty Reward"
        verbose_name_plural = "Loyalty Rewards"
    
    def __str__(self):
        return f"{self.name} ({self.points_required} points)"

    def save(self, *args, **kwargs):
        changed_images = get_changed_image_names(self, LOYALTY_REWARD_IMAGE_VARIANTS.keys())
        validate_changed_image_fields(self, changed_images)
        super().save(*args, **kwargs)
        sync_instance_image_variants(self, LOYALTY_REWARD_IMAGE_VARIANTS, changed_images)
