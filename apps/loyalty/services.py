"""Service functions for loyalty system."""
from decimal import Decimal, ROUND_DOWN

from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import SiteSettings
from apps.offers.models import Offer

from .models import LoyaltySettings, LoyaltyTransaction, ReferralCode, PointsRedemption, RewardWalletItem
from .utils import generate_referral_code, get_loyalty_tier


def get_user_loyalty_summary(user):
    """Get complete loyalty summary for a user."""
    settings = LoyaltySettings.get()
    sync_customer_reward_wallet(user)
    
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
        "referral_total_points": referral_code.total_points_earned,
        "settings": settings,
        "wallet_items": get_available_wallet_items(user),
    }


def get_available_wallet_items(user):
    """Return currently usable reward wallet items for a customer."""
    if not getattr(user, "is_authenticated", False):
        return RewardWalletItem.objects.none()
    now = timezone.now()
    return RewardWalletItem.objects.select_related("offer", "loyalty_reward").filter(
        user=user,
        status=RewardWalletItem.Status.AVAILABLE,
        valid_from__lte=now,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))


def _wallet_expiry(days):
    return timezone.now() + timezone.timedelta(days=days)


def sync_customer_reward_wallet(user):
    """Issue automatic account rewards that should be visible now."""
    if not getattr(user, "is_authenticated", False):
        return

    settings = LoyaltySettings.get()
    site_name = SiteSettings.get().shop_name
    profile = getattr(user, "profile", None)
    now = timezone.localtime()

    if settings.enabled and settings.welcome_bonus > 0:
        RewardWalletItem.objects.get_or_create(
            user=user,
            source=RewardWalletItem.Source.WELCOME,
            offer=None,
            defaults={
                "title": "Welcome reward",
                "description": f"{settings.welcome_bonus} bonus points for joining {site_name}.",
                "points_value": settings.welcome_bonus,
                "expires_at": _wallet_expiry(60),
            },
        )

    birthday = getattr(profile, "date_of_birth", None)
    if settings.enabled and settings.birthday_bonus > 0 and birthday:
        if birthday.month == now.month and birthday.day == now.day:
            RewardWalletItem.objects.get_or_create(
                user=user,
                source=RewardWalletItem.Source.BIRTHDAY,
                title=f"Birthday treat {now.year}",
                defaults={
                    "description": f"{settings.birthday_bonus} birthday points from {site_name}.",
                    "points_value": settings.birthday_bonus,
                    "expires_at": _wallet_expiry(14),
                },
            )

    active_app_offers = Offer.objects.filter(app_exclusive=True, is_active=True)
    for offer in active_app_offers:
        if not offer.supports_checkout_discount() or not offer.is_available_for_user(user, now=now):
            continue
        source = (
            RewardWalletItem.Source.OFF_PEAK
            if offer.audience == Offer.Audience.OFF_PEAK
            else RewardWalletItem.Source.APP_EXCLUSIVE
        )
        RewardWalletItem.objects.get_or_create(
            user=user,
            offer=offer,
            source=source,
            defaults={
                "title": offer.hero_title or offer.name,
                "description": offer.hero_subtitle or offer.description,
                "expires_at": offer.end_date,
            },
        )


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
