from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_offer, create_order, create_user, ensure_site_settings
from apps.loyalty.models import LoyaltyTransaction, RewardWalletItem
from apps.orders.services import get_cart_summary


class LoyaltyViewTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user()
        create_order(user=self.user)
        LoyaltyTransaction.objects.create(
            user=self.user,
            transaction_type=LoyaltyTransaction.TransactionType.BONUS,
            points=50,
            description="Welcome bonus",
        )

    def test_rewards_pages_require_login(self):
        for name in ["loyalty:transactions", "loyalty:refer"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)

    def test_rewards_dashboard_shows_public_join_teaser_when_logged_out(self):
        response = self.client.get(reverse("loyalty:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "loyalty/join.html")
        self.assertContains(response, "Earn points on every order")
        self.assertContains(response, reverse("account_signup"))
        self.assertNotContains(response, "Points Available")

    def test_public_join_teaser_lists_active_offers(self):
        offer = create_offer()
        response = self.client.get(reverse("loyalty:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, offer.name)

    def test_rewards_pages_render_for_logged_in_user(self):
        self.client.force_login(self.user)
        for name in ["loyalty:dashboard", "loyalty:transactions", "loyalty:refer"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_rewards_sync_does_not_create_duplicate_welcome_wallet_reward(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("loyalty:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            RewardWalletItem.objects.filter(
                user=self.user,
                source=RewardWalletItem.Source.WELCOME,
                status=RewardWalletItem.Status.AVAILABLE,
            ).exists()
        )

    def test_rewards_sync_cancels_existing_unused_welcome_wallet_reward(self):
        wallet_item = RewardWalletItem.objects.create(
            user=self.user,
            title="Welcome reward",
            description="Duplicate welcome points",
            source=RewardWalletItem.Source.WELCOME,
            points_value=50,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("loyalty:dashboard"))

        self.assertEqual(response.status_code, 200)
        wallet_item.refresh_from_db()
        self.assertEqual(wallet_item.status, RewardWalletItem.Status.CANCELLED)

    def test_app_exclusive_offer_syncs_to_wallet_and_activates(self):
        offer = create_offer(value=Decimal("20.00"))
        offer.app_exclusive = True
        offer.save(update_fields=["app_exclusive"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("loyalty:dashboard"))

        self.assertEqual(response.status_code, 200)
        wallet_item = RewardWalletItem.objects.get(user=self.user, offer=offer)
        response = self.client.post(reverse("loyalty:activate_wallet_item", args=[wallet_item.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["reward_wallet_item_id"], wallet_item.pk)

    def test_wallet_reward_applies_discount_and_marks_used_on_order_creation(self):
        from apps.orders.services import create_order_from_summary

        offer = create_offer(value=Decimal("5.00"), offer_type="fixed")
        wallet_item = RewardWalletItem.objects.create(
            user=self.user,
            title="App reward",
            description="Five pounds off",
            offer=offer,
        )
        cart = {
            "line-1": {
                "menu_item_id": "1",
                "name": "Test meal",
                "price": "12.50",
                "quantity": 1,
                "modifiers": [],
            }
        }

        summary = get_cart_summary(cart, user=self.user, reward_wallet_item_id=wallet_item.pk)

        self.assertEqual(summary["discount"], Decimal("5.00"))
        order = create_order_from_summary(
            summary,
            customer_name="Test User",
            customer_phone="07747055935",
            user=self.user,
        )
        wallet_item.refresh_from_db()
        self.assertEqual(wallet_item.status, RewardWalletItem.Status.USED)
        self.assertEqual(wallet_item.used_order, order)
