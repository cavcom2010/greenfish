from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_order, create_user, ensure_site_settings
from apps.loyalty.models import LoyaltyTransaction


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
        for name in ["loyalty:dashboard", "loyalty:transactions", "loyalty:refer"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)

    def test_rewards_pages_render_for_logged_in_user(self):
        self.client.force_login(self.user)
        for name in ["loyalty:dashboard", "loyalty:transactions", "loyalty:refer"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
