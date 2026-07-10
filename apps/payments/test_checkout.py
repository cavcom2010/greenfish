from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.test_support import create_menu_item, create_order, create_user, ensure_site_settings
from apps.orders.models import Order
from apps.payments.models import Payment

# Note: broad create_payment/demo_checkout happy-path coverage (Stripe checkout
# creation, payment fallback, delivery details, demo "pay" action, etc.) already
# lives in apps.orders.tests.PaymentFlowTests. These tests cover the gaps left
# by that suite: demo_checkout's debug/provider gate, its "cancel" action, and
# create_payment's empty-cart rejection.


class DemoCheckoutGateTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user()
        self.order = create_order(user=self.user, status=Order.OrderStatus.PENDING)

    def _url(self):
        return f"{reverse('payments:demo_checkout', args=[self.order.order_number])}?t={self.order.public_access_token}"

    @override_settings(DEBUG=False, PAYMENT_PROVIDER="stripe")
    def test_404_outside_debug_mode(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_live_realkeylongenoughtopass",
        STRIPE_WEBHOOK_SECRET="whsec_realsecretlongenoughtopass",
    )
    def test_404_when_real_provider_is_configured_even_in_debug(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    @override_settings(DEBUG=True, PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="")
    def test_200_when_enabled(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/demo_checkout.html")

    @override_settings(DEBUG=True, PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="")
    def test_cancel_action_marks_payment_and_order_cancelled(self):
        payment = Payment.objects.create(
            order=self.order,
            provider=Payment.Provider.DEMO,
            external_payment_id="demo_cancel_1",
            amount=self.order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )
        response = self.client.post(self._url(), {"action": "cancel"})

        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CANCELLED)
        self.assertEqual(self.order.status, Order.OrderStatus.CANCELLED)


class CreatePaymentEmptyCartTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.menu_item = create_menu_item()

    @override_settings(PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="")
    def test_empty_cart_is_rejected_without_creating_order_or_payment(self):
        response = self.client.post(
            reverse("payments:create"),
            {
                "service_type": Order.ServiceType.PICKUP,
                "customer_name": "No Cart Customer",
                "customer_phone": "07747055935",
                "customer_email": "nocart@example.com",
                "pickup_time": "15",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
