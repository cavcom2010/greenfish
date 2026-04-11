"""Signals for loyalty system."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import SiteSettings
from apps.orders.models import Order

from .services import award_points_for_order
from .models import LoyaltySettings, ReferralCode
from .utils import generate_referral_code


@receiver(post_save, sender=Order)
def award_points_on_completion(sender, instance, created, **kwargs):
    """Award points when an order is marked as completed."""
    if instance.status == Order.OrderStatus.COMPLETED:
        # Check if points already awarded for this order
        from .models import LoyaltyTransaction
        existing = LoyaltyTransaction.objects.filter(
            order=instance,
            transaction_type=LoyaltyTransaction.TransactionType.EARNED
        ).exists()
        
        if not existing:
            award_points_for_order(instance)


@receiver(post_save, sender="accounts.User")
def create_referral_code_for_new_user(sender, instance, created, **kwargs):
    """Create referral code for new users."""
    if created:
        ReferralCode.objects.get_or_create(
            user=instance,
            defaults={"code": generate_referral_code()}
        )
        
        # Give welcome bonus
        settings = LoyaltySettings.get()
        if settings.enabled and settings.welcome_bonus > 0:
            from .models import LoyaltyTransaction
            LoyaltyTransaction.objects.create(
                user=instance,
                transaction_type=LoyaltyTransaction.TransactionType.BONUS,
                points=settings.welcome_bonus,
                description=f"Welcome bonus for joining {SiteSettings.get().shop_name}!"
            )
