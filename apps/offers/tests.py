from decimal import Decimal
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CustomerProfile
from apps.core.test_support import create_offer, create_order, create_user, ensure_site_settings
from apps.offers.models import Offer
from apps.orders.models import Order


class OfferAudienceTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="offers@example.com")

    def test_first_order_offer_excludes_paid_existing_customers(self):
        offer = create_offer(value=Decimal("10.00"))
        offer.audience = Offer.Audience.FIRST_ORDER
        offer.save(update_fields=["audience"])

        self.assertTrue(offer.is_available_for_user(self.user))

        create_order(user=self.user, payment_status=Order.PaymentStatus.PAID)

        self.assertFalse(offer.is_available_for_user(self.user))

    def test_birthday_offer_requires_matching_customer_birthday(self):
        offer = create_offer(value=Decimal("10.00"))
        offer.audience = Offer.Audience.BIRTHDAY
        offer.save(update_fields=["audience"])
        profile, _ = CustomerProfile.objects.get_or_create(user=self.user)
        profile.date_of_birth = timezone.localdate()
        profile.save(update_fields=["date_of_birth"])

        self.assertTrue(offer.is_available_for_user(self.user))

    def test_off_peak_offer_uses_time_window(self):
        offer = create_offer(value=Decimal("10.00"))
        offer.audience = Offer.Audience.OFF_PEAK
        offer.off_peak_start = datetime(2026, 1, 1, 14, 0).time()
        offer.off_peak_end = datetime(2026, 1, 1, 16, 0).time()
        offer.save(update_fields=["audience", "off_peak_start", "off_peak_end"])
        inside_window = timezone.make_aware(datetime(2026, 1, 1, 15, 0))
        outside_window = timezone.make_aware(datetime(2026, 1, 1, 18, 0))

        self.assertTrue(offer.is_available_for_user(self.user, now=inside_window))
        self.assertFalse(offer.is_available_for_user(self.user, now=outside_window))
