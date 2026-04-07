"""Service functions for loyalty system."""
from decimal import Decimal, ROUND_DOWN

from django.db.models import Sum

from .models import LoyaltySettings, LoyaltyTransaction, ReferralCode, PointsRedemption
from .utils import generate_referral_code, get_loyalty_tier


def get_user_loyalty_summary(user):
    """Get complete loyalty summary for a user."""
    settings = LoyaltySettings.get()
    
    # Calculate current balance
    balance_data = LoyaltyTransaction.objects.filter(user=user).aggregate(
        total=Sum("points")
    )
    current_points = balance_data["total"] or 0
    
    # Calculate lifetime points earned (for tier)
    lifetime_data = LoyaltyTransaction.objects.filter(
        user=user,
        transaction_type__in=["earned", "bonus", "referral", "birthday"]
    ).aggregate(total=Sum("points"))
    lifetime_points = lifetime_data["total"] or 0
    
    # Get tier info
    tier = get_loyalty_tier(lifetime_points)
    
    # Get recent transactions
    recent_transactions = LoyaltyTransaction.objects.filter(user=user)[:10]
    
    # Calculate points value
    points_value = Decimal(current_points) * settings.points_value
    
    # Get or create referral code
    referral_code, _ = ReferralCode.objects.get_or_create(
        user=user,
        defaults={"code": generate_referral_code()}
    )
    
    return {
        "current_points": current_points,
        "lifetime_points": lifetime_points,
        "points_value": points_value.quantize(Decimal("0.01")),
        "tier": tier,
        "recent_transactions": recent_transactions,
        "referral_code": referral_code.code,
        "referral_count": referral_code.successful_referrals,
        "settings": settings,
    }


def award_points_for_order(order):
    """Award loyalty points for a completed order."""
    settings = LoyaltySettings.get()
    if not settings.enabled:
        return None
    
    user = order.user
    if not user:
        return None  # Guest orders don't earn points
    
    # Calculate base points
    order_total = order.subtotal  # Excludes delivery
    base_points = (order_total * settings.points_per_pound).quantize(
        Decimal("1"), rounding=ROUND_DOWN
    )
    
    # Apply tier multiplier
    lifetime = LoyaltyTransaction.objects.filter(
        user=user,
        transaction_type__in=["earned", "bonus", "referral", "birthday"]
    ).aggregate(total=Sum("points"))["total"] or 0
    tier = get_loyalty_tier(lifetime)
    multiplier = tier["multiplier"]
    
    final_points = int(base_points * Decimal(str(multiplier)))
    
    if final_points > 0:
        transaction = LoyaltyTransaction.objects.create(
            user=user,
            order=order,
            transaction_type=LoyaltyTransaction.TransactionType.EARNED,
            points=final_points,
            description=f"Points earned for order #{order.order_number}"
        )
        return transaction
    return None


def calculate_max_redeemable_points(user, order_total):
    """Calculate maximum points user can redeem for an order."""
    settings = LoyaltySettings.get()
    if not settings.enabled:
        return 0
    
    # Get current balance
    balance_data = LoyaltyTransaction.objects.filter(user=user).aggregate(
        total=Sum("points")
    )
    current_points = balance_data["total"] or 0
    
    if current_points < settings.min_points_redeem:
        return 0
    
    # Calculate max discount amount
    max_discount = (order_total * settings.max_discount_percent / 100).quantize(
        Decimal("0.01")
    )
    
    # Convert to points
    max_points_for_discount = int(max_discount / settings.points_value)
    
    # Return minimum of available points and max allowed
    return min(current_points, max_points_for_discount)


def redeem_points_for_order(user, order, points_to_redeem):
    """Redeem points for an order discount."""
    settings = LoyaltySettings.get()
    
    # Validate
    max_redeemable = calculate_max_redeemable_points(user, order.subtotal)
    if points_to_redeem > max_redeemable:
        raise ValueError(f"Cannot redeem more than {max_redeemable} points")
    
    # Calculate discount
    discount = Decimal(points_to_redeem) * settings.points_value
    discount = discount.quantize(Decimal("0.01"))
    
    # Create transaction
    LoyaltyTransaction.objects.create(
        user=user,
        order=order,
        transaction_type=LoyaltyTransaction.TransactionType.REDEEMED,
        points=-points_to_redeem,
        description=f"Points redeemed for order #{order.order_number}"
    )
    
    # Create redemption record
    redemption = PointsRedemption.objects.create(
        user=user,
        order=order,
        points_used=points_to_redeem,
        discount_amount=discount
    )
    
    return redemption


def apply_referral_bonus(new_user, referral_code_str):
    """Apply referral bonus when a new user signs up with a code."""
    settings = LoyaltySettings.get()
    if not settings.enabled or not settings.enable_referral:
        return False
    
    try:
        referrer_code = ReferralCode.objects.select_related("user").get(
            code=referral_code_str.upper()
        )
        
        # Don't allow self-referral
        if referrer_code.user == new_user:
            return False
        
        # Record the referral
        referrer_code.record_referral(new_user)
        return True
        
    except ReferralCode.DoesNotExist:
        return False


def give_welcome_bonus(user):
    """Give welcome bonus to new users."""
    settings = LoyaltySettings.get()
    if not settings.enabled or settings.welcome_bonus <= 0:
        return None
    
    transaction = LoyaltyTransaction.objects.create(
        user=user,
        transaction_type=LoyaltyTransaction.TransactionType.BONUS,
        points=settings.welcome_bonus,
        description=f"Welcome bonus for joining {SiteSettings.get().shop_name}!"
    )
    return transaction
