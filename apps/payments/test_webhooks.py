from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.test_support import create_order
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentLog, PaymentWebhookEvent


def _make_payment(provider, external_payment_id, status=Payment.Status.PENDING):
    order = create_order(payment_status=Order.PaymentStatus.PENDING)
    return Payment.objects.create(
        order=order,
        provider=provider,
        external_payment_id=external_payment_id,
        amount=Decimal("12.50"),
        currency="GBP",
        status=status,
    )


@override_settings(PAYMENT_PROVIDER="stripe", STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookTests(TestCase):
    def _fake_event(self, checkout_session_id, event_type="checkout.session.completed", event_id="evt_1"):
        return {
            "id": event_id,
            "type": event_type,
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
    def test_valid_signature_processes_checkout_completed(self, mock_construct_event):
        payment = _make_payment(Payment.Provider.STRIPE, "cs_test_1")
        mock_construct_event.return_value = self._fake_event("cs_test_1")

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        webhook_event = PaymentWebhookEvent.objects.get(provider=Payment.Provider.STRIPE, event_id="evt_1")
        self.assertIsNotNone(webhook_event.processed_at)
        self.assertTrue(
            PaymentLog.objects.filter(payment=payment, event_type="webhook_received").exists()
        )

    @patch("apps.payments.views.stripe.Webhook.construct_event")
    def test_invalid_signature_rejected(self, mock_construct_event):
        from apps.payments.views import stripe_error

        mock_construct_event.side_effect = stripe_error.SignatureVerificationError("bad sig", "sig")

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="bad",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PaymentWebhookEvent.objects.exists())

    @patch("apps.payments.views.stripe.Webhook.construct_event")
    def test_missing_payload_rejected(self, mock_construct_event):
        mock_construct_event.side_effect = ValueError("bad payload")

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"not json",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )

        self.assertEqual(response.status_code, 400)

    @patch("apps.payments.services.StripePaymentService.update_payment_status")
    @patch("apps.payments.views.stripe.Webhook.construct_event")
    def test_duplicate_event_is_noop(self, mock_construct_event, mock_update_status):
        payment = _make_payment(Payment.Provider.STRIPE, "cs_test_2")
        PaymentWebhookEvent.objects.create(
            provider=Payment.Provider.STRIPE,
            event_id="evt_dup",
            event_type="checkout.session.completed",
            payment=payment,
            processed_at=timezone.now(),
        )
        mock_construct_event.return_value = self._fake_event("cs_test_2", event_id="evt_dup")

        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )

        self.assertEqual(response.status_code, 200)
        mock_update_status.assert_not_called()

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_missing_webhook_secret_fails_closed(self):
        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )

        self.assertEqual(response.status_code, 403)


@override_settings(PAYMENT_PROVIDER="mollie", STRIPE_WEBHOOK_SECRET="")
class LegacyProviderConfigTests(TestCase):
    def test_unknown_provider_normalises_to_stripe_and_fails_closed(self):
        response = self.client.post(
            reverse("payments:webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="sig",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PaymentWebhookEvent.objects.exists())
