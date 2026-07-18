"""Regression tests for money-path concurrency and state-machine guards."""
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.test_support import create_menu_item, create_order, create_user, create_voucher
from apps.loyalty.models import LoyaltyTransaction, RewardWalletItem
from apps.loyalty.services import award_points_for_order, redeem_points_for_order
from apps.menu.models import StockMovement
from apps.offers.models import Offer, VoucherUsage
from apps.orders.models import Order, OrderStatusHistory
from apps.payments.models import Payment, PaymentWebhookEvent, RefundRequest
from apps.payments.services import (
    _apply_local_payment_state,
    expire_offline_pending_payment,
    process_refund_request,
)


def _make_payment(order, provider=Payment.Provider.STRIPE, status=Payment.Status.PENDING, **extra):
    return Payment.objects.create(
        order=order,
        provider=provider,
        external_payment_id=extra.pop("external_payment_id", "cs_test_ms"),
        amount=order.total_amount,
        currency="GBP",
        status=status,
        **extra,
    )


class MarkAsPaidIdempotencyTests(TestCase):
    def test_mark_as_paid_only_wins_once(self):
        order = create_order(status=Order.OrderStatus.PENDING)

        self.assertTrue(order.mark_as_paid())
        self.assertFalse(order.mark_as_paid())

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=order, new_status=Order.OrderStatus.CONFIRMED).count(),
            1,
        )

    def test_consume_stock_is_idempotent(self):
        item = create_menu_item(name="Tracked Wings", track_stock=True, stock_quantity=10)
        order = create_order(status=Order.OrderStatus.PENDING)
        StockMovement.objects.create(
            menu_item=item,
            order=order,
            movement_type=StockMovement.MovementType.RESERVED,
            quantity=-2,
        )

        from apps.orders.inventory import consume_order_stock

        consume_order_stock(order)
        consume_order_stock(order)

        self.assertEqual(
            order.stock_movements.filter(movement_type=StockMovement.MovementType.CONSUMED).count(),
            1,
        )

    def test_release_stock_is_idempotent(self):
        item = create_menu_item(name="Tracked Fish", track_stock=True, stock_quantity=8)
        order = create_order(status=Order.OrderStatus.PENDING)
        StockMovement.objects.create(
            menu_item=item,
            order=order,
            movement_type=StockMovement.MovementType.RESERVED,
            quantity=-3,
        )

        from apps.orders.inventory import release_order_stock

        release_order_stock(order)
        release_order_stock(order)

        item.refresh_from_db()
        self.assertEqual(item.stock_quantity, 11)
        self.assertEqual(
            order.stock_movements.filter(movement_type=StockMovement.MovementType.RELEASED).count(),
            1,
        )


class OrderStatusMachineTests(TestCase):
    def test_pending_cannot_jump_to_completed(self):
        order = create_order(status=Order.OrderStatus.PENDING)
        with self.assertRaises(ValidationError):
            order.update_status(Order.OrderStatus.COMPLETED)

    def test_completed_is_terminal(self):
        order = create_order(status=Order.OrderStatus.COMPLETED)
        with self.assertRaises(ValidationError):
            order.update_status(Order.OrderStatus.PREPARING)

    def test_cancelled_is_terminal(self):
        order = create_order(status=Order.OrderStatus.CANCELLED)
        with self.assertRaises(ValidationError):
            order.update_status(Order.OrderStatus.CONFIRMED)

    def test_forward_flow_allowed(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        order.update_status(Order.OrderStatus.PREPARING)
        order.update_status(Order.OrderStatus.READY)
        order.update_status(Order.OrderStatus.COMPLETED)
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)


class PaymentStateTransitionTests(TestCase):
    def test_paid_payment_ignores_stale_expiry_event(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        payment = _make_payment(order, status=Payment.Status.PAID)

        _apply_local_payment_state(payment, new_status=Payment.Status.EXPIRED, provider_status="expired")

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_paid_payment_can_be_refunded(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        payment = _make_payment(order, status=Payment.Status.PAID)

        _apply_local_payment_state(payment, new_status=Payment.Status.REFUNDED, provider_status="refunded")

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REFUNDED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_expired_offline_payment_cannot_be_expired_twice(self):
        order = create_order(status=Order.OrderStatus.PENDING)
        payment = _make_payment(order, provider=Payment.Provider.OFFLINE_PENDING)

        expire_offline_pending_payment(payment)
        first_logs = payment.logs.filter(event_type="offline_payment_expired").count()
        expire_offline_pending_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.EXPIRED)
        self.assertEqual(payment.logs.filter(event_type="offline_payment_expired").count(), first_logs)

    def test_paid_offline_payment_is_not_expired(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        payment = _make_payment(order, provider=Payment.Provider.OFFLINE_PENDING, status=Payment.Status.PAID)

        expire_offline_pending_payment(payment)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)


class VoucherRaceGuardTests(TestCase):
    def test_voucher_usage_limit_enforced_at_record_time(self):
        voucher = create_voucher(code="ONCE")
        voucher.max_uses = 1
        voucher.save(update_fields=["max_uses"])

        voucher.record_usage()
        with self.assertRaises(ValidationError):
            voucher.record_usage()

        voucher.refresh_from_db()
        self.assertEqual(voucher.uses_count, 1)

    def test_per_customer_limit_enforced_at_record_time(self):
        user = create_user(email="voucher@example.com")
        voucher = create_voucher(code="PERUSER")
        voucher.max_uses_per_customer = 1
        voucher.save(update_fields=["max_uses_per_customer"])

        voucher.record_usage(user=user)
        with self.assertRaises(ValidationError):
            voucher.record_usage(user=user)

        self.assertEqual(VoucherUsage.objects.filter(voucher=voucher, user=user).count(), 1)

    def test_offer_usage_cap_enforced(self):
        voucher = create_voucher(code="OFFERCAP")
        offer = voucher.offer
        offer.max_usage_count = 1
        offer.save(update_fields=["max_usage_count"])

        offer.increment_usage()
        with self.assertRaises(ValidationError):
            offer.increment_usage()

        offer.refresh_from_db()
        self.assertEqual(offer.usage_count, 1)


class LoyaltyRaceGuardTests(TestCase):
    def test_points_awarded_once_per_order(self):
        user = create_user(email="loyal@example.com")
        order = create_order(user=user, status=Order.OrderStatus.COMPLETED, payment_status=Order.PaymentStatus.PAID)

        LoyaltyTransaction.objects.filter(user=user).delete()
        first = award_points_for_order(order)
        second = award_points_for_order(order)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(
                order=order, transaction_type=LoyaltyTransaction.TransactionType.EARNED
            ).count(),
            1,
        )

    def test_cannot_redeem_more_points_than_balance(self):
        user = create_user(email="redeem@example.com")
        order = create_order(user=user)
        LoyaltyTransaction.objects.filter(user=user).delete()
        LoyaltyTransaction.objects.create(
            user=user,
            transaction_type=LoyaltyTransaction.TransactionType.BONUS,
            points=50,
        )

        with self.assertRaises(ValueError):
            redeem_points_for_order(user, order, 100000)

    def test_wallet_item_claimed_once(self):
        user = create_user(email="wallet@example.com")
        wallet_item = RewardWalletItem.objects.create(
            user=user,
            source=RewardWalletItem.Source.WELCOME,
            title="Test reward",
            points_value=25,
        )

        wallet_item.mark_used(None)
        with self.assertRaises(ValidationError):
            RewardWalletItem.objects.get(pk=wallet_item.pk).mark_used(None)


class RefundGuardTests(TestCase):
    def test_refund_amount_cannot_exceed_payment(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        payment = _make_payment(order, status=Payment.Status.PAID)
        refund = RefundRequest.objects.create(payment=payment, amount=Decimal("999.99"), reason="test")

        result = process_refund_request(refund)

        self.assertEqual(result.status, RefundRequest.Status.FAILED)
        self.assertIn("cannot exceed", result.error_message)

    def test_processed_refund_is_not_reprocessed(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        payment = _make_payment(order, status=Payment.Status.PAID)
        refund = RefundRequest.objects.create(
            payment=payment,
            amount=None,
            reason="test",
            status=RefundRequest.Status.SUCCEEDED,
        )

        with patch("apps.payments.services.StripePaymentService.refund_payment") as mock_refund:
            result = process_refund_request(refund)

        mock_refund.assert_not_called()
        self.assertEqual(result.status, RefundRequest.Status.SUCCEEDED)

    @override_settings(STRIPE_SECRET_KEY="sk_test_x")
    def test_stripe_refund_fetches_payment_intent_from_session(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        payment = _make_payment(order, status=Payment.Status.PAID, metadata={})

        from apps.payments.services import StripePaymentService

        with patch("apps.payments.services.stripe.checkout.Session.retrieve") as mock_retrieve, patch(
            "apps.payments.services.stripe.Refund.create"
        ) as mock_refund_create:
            mock_retrieve.return_value = {"payment_intent": "pi_test_123"}
            success = StripePaymentService().refund_payment(payment)

        self.assertTrue(success)
        mock_refund_create.assert_called_once_with(payment_intent="pi_test_123")


@override_settings(PAYMENT_PROVIDER="stripe", STRIPE_WEBHOOK_SECRET="whsec_test")
class WebhookClaimTests(TestCase):
    def _fake_event(self, checkout_session_id, event_id="evt_claim"):
        return {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": checkout_session_id,
                    "status": "complete",
                    "payment_status": "paid",
                    "payment_method_types": ["card"],
                }
            },
        }

    @patch("apps.payments.views.stripe.Webhook.construct_event")
    def test_processing_failure_releases_claim_for_retry(self, mock_construct_event):
        order = create_order(status=Order.OrderStatus.PENDING)
        _make_payment(order, external_payment_id="cs_claim_1")
        mock_construct_event.return_value = self._fake_event("cs_claim_1")

        with patch(
            "apps.payments.services.StripePaymentService.update_payment_status",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post(
                reverse("payments:webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig",
            )

        self.assertEqual(response.status_code, 500)
        event = PaymentWebhookEvent.objects.get(event_id="evt_claim")
        self.assertIsNone(event.processed_at)

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)

    @patch("apps.payments.views.stripe.Webhook.construct_event")
    def test_duplicate_delivery_processes_payment_once(self, mock_construct_event):
        order = create_order(status=Order.OrderStatus.PENDING)
        _make_payment(order, external_payment_id="cs_claim_2")
        mock_construct_event.return_value = self._fake_event("cs_claim_2", event_id="evt_dup_claim")

        for _ in range(2):
            response = self.client.post(
                reverse("payments:webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="sig",
            )
            self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=order, new_status=Order.OrderStatus.CONFIRMED).count(),
            1,
        )
