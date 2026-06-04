"""Admin configuration for loyalty app."""
from django.contrib import admin

from .models import (
    LoyaltySettings,
    LoyaltyTransaction,
    ReferralCode,
    PointsRedemption,
    LoyaltyReward,
    RewardWalletItem,
)


@admin.register(LoyaltySettings)
class LoyaltySettingsAdmin(admin.ModelAdmin):
    list_display = [
        "enabled",
        "points_per_pound",
        "points_value",
        "min_points_redeem",
        "max_discount_percent",
    ]
    
    def has_add_permission(self, request):
        # Only allow one settings object
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "transaction_type",
        "points",
        "order",
        "created_at",
    ]
    list_filter = ["transaction_type", "created_at"]
    search_fields = ["user__email", "description"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "user", "successful_referrals", "total_points_earned", "created_at"]
    search_fields = ["code", "user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["code", "created_at"]


@admin.register(PointsRedemption)
class PointsRedemptionAdmin(admin.ModelAdmin):
    list_display = ["user", "order", "points_used", "discount_amount", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email", "order__order_number"]
    readonly_fields = ["created_at"]


@admin.register(LoyaltyReward)
class LoyaltyRewardAdmin(admin.ModelAdmin):
    list_display = ["name", "points_required", "reward_type", "is_active", "created_at"]
    list_filter = ["reward_type", "is_active"]
    search_fields = ["name", "description"]


@admin.register(RewardWalletItem)
class RewardWalletItemAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "source", "status", "offer", "points_value", "expires_at", "used_at"]
    list_filter = ["source", "status", "expires_at", "created_at"]
    search_fields = ["title", "description", "user__email", "offer__name"]
    readonly_fields = ["created_at", "updated_at", "used_at"]
    autocomplete_fields = ["user", "offer", "loyalty_reward", "used_order"]
