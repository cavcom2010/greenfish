from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.test_support import create_menu_item, create_order, create_user, ensure_site_settings
from apps.loyalty.models import LoyaltySettings, LoyaltyTransaction
from apps.loyalty.services import award_points_for_order, calculate_max_redeemable_points


class AwardPointsForOrderTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="loyaltyuser@example.com")
        self.settings = LoyaltySettings.get()
        self.settings.enabled = True
        self.settings.points_per_pound = Decimal("1.00")
        self.settings.save()

    def test_points_are_subtotal_times_points_per_pound_floored(self):
        order = create_order(user=self.user, subtotal=Decimal("12.50"), total_amount=Decimal("12.50"))

        result = award_points_for_order(order)

        self.assertIsNotNone(result)
        self.assertEqual(result.points, 12)
        self.assertEqual(result.transaction_type, LoyaltyTransaction.TransactionType.EARNED)

    def test_guest_order_user_none_earns_nothing(self):
        order = create_order(user=None, subtotal=Decimal("50.00"), total_amount=Decimal("50.00"))

        result = award_points_for_order(order)

        self.assertIsNone(result)

    def test_disabled_settings_earns_nothing(self):
        self.settings.enabled = False
        self.settings.save()
        order = create_order(user=self.user, subtotal=Decimal("50.00"), total_amount=Decimal("50.00"))

        result = award_points_for_order(order)

        self.assertIsNone(result)


class CalculateMaxRedeemablePointsTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="redeemuser@example.com")
        self.settings = LoyaltySettings.get()
        self.settings.enabled = True
        self.settings.points_value = Decimal("0.01")
        self.settings.min_points_redeem = 100
        self.settings.max_discount_percent = 50
        self.settings.save()

    def test_zero_when_below_min_points_redeem(self):
        self.assertEqual(calculate_max_redeemable_points(self.user, Decimal("100.00")), 0)

    def test_capped_by_max_discount_percent_of_order_total(self):
        LoyaltyTransaction.objects.create(
            user=self.user,
            transaction_type=LoyaltyTransaction.TransactionType.BONUS,
            points=500,
            description="Bonus",
        )

        max_points = calculate_max_redeemable_points(self.user, Decimal("6.00"))

        self.assertEqual(max_points, 300)

    def test_uses_full_balance_when_under_cap(self):
        LoyaltyTransaction.objects.create(
            user=self.user,
            transaction_type=LoyaltyTransaction.TransactionType.BONUS,
            points=150,
            description="Bonus",
        )

        max_points = calculate_max_redeemable_points(self.user, Decimal("100.00"))

        self.assertEqual(max_points, 200)

    def test_disabled_settings_returns_zero(self):
        self.settings.enabled = False
        self.settings.save()
        LoyaltyTransaction.objects.create(
            user=self.user,
            transaction_type=LoyaltyTransaction.TransactionType.BONUS,
            points=500,
            description="Bonus",
        )

        self.assertEqual(calculate_max_redeemable_points(self.user, Decimal("100.00")), 0)
