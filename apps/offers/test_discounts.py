from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.test_support import create_menu_item, create_offer, create_order, create_voucher, create_user, ensure_site_settings
from apps.offers.models import Offer, VoucherCode
from apps.orders.services import get_cart_summary


class OfferCalculateDiscountTests(TestCase):
    def setUp(self):
        ensure_site_settings()

    def test_percentage_discount_computes_correctly_and_quantizes_to_2dp(self):
        offer = create_offer(value=Decimal("15.50"), offer_type=Offer.OfferType.PERCENTAGE)

        discount = offer.calculate_discount(Decimal("100.00"))

        self.assertEqual(discount, Decimal("15.50"))

    def test_fixed_discount_caps_at_base_amount(self):
        offer = create_offer(value=Decimal("50.00"), offer_type=Offer.OfferType.FIXED)

        discount = offer.calculate_discount(Decimal("30.00"))

        self.assertEqual(discount, Decimal("30.00"))

    def test_discount_zero_when_below_minimum_order_amount(self):
        offer = create_offer(value=Decimal("10.00"), offer_type=Offer.OfferType.FIXED)
        offer.minimum_order_amount = Decimal("20.00")
        offer.save(update_fields=["minimum_order_amount"])

        discount = offer.calculate_discount(Decimal("15.00"))

        self.assertEqual(discount, Decimal("0.00"))

    def test_inactive_offer_gives_zero_discount(self):
        offer = create_offer(value=Decimal("10.00"), offer_type=Offer.OfferType.FIXED)
        offer.is_active = False
        offer.save(update_fields=["is_active"])

        discount = offer.calculate_discount(Decimal("100.00"))

        self.assertEqual(discount, Decimal("0.00"))

    def test_expired_offer_gives_zero_discount(self):
        now = timezone.now()
        offer = create_offer(value=Decimal("10.00"), offer_type=Offer.OfferType.FIXED)
        offer.end_date = now - timezone.timedelta(days=1)
        offer.save(update_fields=["end_date"])

        discount = offer.calculate_discount(Decimal("100.00"))

        self.assertEqual(discount, Decimal("0.00"))


class VoucherCodeIsValidTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="vouchertest@example.com")

    def test_outside_valid_from_date_is_invalid(self):
        now = timezone.now()
        voucher = create_voucher(code="EXPIRED1")
        voucher.valid_from = now + timezone.timedelta(days=1)
        voucher.save(update_fields=["valid_from"])

        self.assertFalse(voucher.is_valid())

    def test_outside_valid_until_date_is_invalid(self):
        now = timezone.now()
        voucher = create_voucher(code="EXPIRED2")
        voucher.valid_until = now - timezone.timedelta(days=1)
        voucher.save(update_fields=["valid_until"])

        self.assertFalse(voucher.is_valid())

    def test_voucher_invalid_when_offer_is_inactive(self):
        offer = create_offer()
        offer.is_active = False
        offer.save(update_fields=["is_active"])
        voucher = create_voucher(code="BADOFFER", offer=offer)

        self.assertFalse(voucher.is_valid())

    def test_guest_max_uses_per_customer_blocks_by_phone_match(self):
        voucher = create_voucher(code="G11")
        voucher.max_uses_per_customer = 1
        voucher.save(update_fields=["max_uses_per_customer"])

        create_order(
            customer_phone="07747055935",
            voucher_code=voucher.code,
        )

        self.assertFalse(voucher.is_valid(guest_phone="07747 055935"))
        self.assertTrue(voucher.is_valid(guest_phone="07800000001"))


class CartSummaryVoucherTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.menu_item = create_menu_item()

    def test_get_cart_summary_applies_valid_voucher_discount_to_totals(self):
        offer = create_offer(value=Decimal("10.00"), offer_type=Offer.OfferType.FIXED)
        voucher = create_voucher(code="CART10", offer=offer)

        cart = {
            "item-1": {
                "menu_item_id": self.menu_item.pk,
                "name": self.menu_item.name,
                "price": str(self.menu_item.price),
                "quantity": 1,
                "modifiers": [],
            }
        }

        summary = get_cart_summary(cart, voucher_code=voucher.code)

        self.assertIsNotNone(summary["voucher"])
        self.assertEqual(summary["voucher"].code, voucher.code)
        self.assertEqual(summary["discount"], Decimal("10.00"))
        self.assertEqual(summary["subtotal"], Decimal("12.50"))
        self.assertEqual(summary["total"], Decimal("2.50"))
