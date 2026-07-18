from decimal import Decimal

from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.test_support import create_menu_item, ensure_site_settings
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.services import create_offline_pending_payment, expire_offline_pending_payment, expire_due_offline_payments, record_manual_payment


class PaymentFallbackFlowTests(TestCase):
    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        PAYMENT_FALLBACK_ENABLED=True,
        DEMO_CHECKOUT_ENABLED=False,
    )
    def test_end_to_end_fallback_flow(self):
        ensure_site_settings()
        self.menu_item = create_menu_item()

        add_url = reverse("orders:add_to_cart")
        self.client.post(
            add_url,
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )

        create_url = reverse("payments:create")
        response = self.client.post(
            create_url,
            {
                "service_type": Order.ServiceType.PICKUP,
                "customer_name": "Fallback User",
                "customer_phone": "07747055935",
                "customer_email": "fallback@example.com",
                "pickup_time": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "payment_fallback_prompt",
            self.client.session,
            "Fallback prompt should be stored in session",
        )

        response = self.client.post(
            create_url,
            {
                "service_type": Order.ServiceType.PICKUP,
                "customer_name": "Fallback User",
                "customer_phone": "07747055935",
                "customer_email": "fallback@example.com",
                "pickup_time": "15",
                "payment_fallback_acknowledged": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

        payment = Payment.objects.get()
        self.assertEqual(payment.provider, Payment.Provider.OFFLINE_PENDING)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        order = payment.order
        self.assertEqual(order.status, Order.OrderStatus.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        PAYMENT_FALLBACK_ENABLED=True,
        DEMO_CHECKOUT_ENABLED=False,
    )
    def test_record_manual_payment_completes_order(self):
        ensure_site_settings()
        self.menu_item = create_menu_item()

        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )

        self.client.post(
            reverse("payments:create"),
            {
                "service_type": Order.ServiceType.PICKUP,
                "customer_name": "Manual User",
                "customer_phone": "07747055935",
                "customer_email": "manual@example.com",
                "pickup_time": "15",
            },
        )

        self.client.post(
            reverse("payments:create"),
            {
                "service_type": Order.ServiceType.PICKUP,
                "customer_name": "Manual User",
                "customer_phone": "07747055935",
                "customer_email": "manual@example.com",
                "pickup_time": "15",
                "payment_fallback_acknowledged": "1",
            },
        )

        payment = Payment.objects.get()

        with transaction.atomic():
            record_manual_payment(
                payment,
                method="cash",
                amount_received=payment.amount,
                reference_code="R1",
            )

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        order = payment.order
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CONFIRMED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_record_manual_payment_amount_below_total_raises_ValueError(self):
        ensure_site_settings()
        order = Order.objects.create(
            customer_name="Underpay User",
            customer_phone="07747055935",
            subtotal=Decimal("12.50"),
            total_amount=Decimal("12.50"),
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            requested_pickup_time=timezone.now() + timezone.timedelta(minutes=15),
        )
        from apps.payments.services import create_offline_pending_payment
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        payment = create_offline_pending_payment(order, request)

        with self.assertRaises(ValueError) as ctx:
            with transaction.atomic():
                record_manual_payment(
                    payment,
                    method="cash",
                    amount_received=Decimal("5.00"),
                    reference_code="R2",
                )
        self.assertIn("Amount received must be at least the order total", str(ctx.exception))

    def test_expire_offline_pending_payment_cancels_expired_hold(self):
        ensure_site_settings()
        order = Order.objects.create(
            customer_name="Expired User",
            customer_phone="07747055935",
            subtotal=Decimal("12.50"),
            total_amount=Decimal("12.50"),
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            requested_pickup_time=timezone.now() + timezone.timedelta(minutes=15),
        )
        from apps.payments.services import create_offline_pending_payment
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        payment = create_offline_pending_payment(order, request)
        payment.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        payment.save(update_fields=["expires_at"])

        expire_offline_pending_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.EXPIRED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)

    def test_expire_due_offline_payments_handles_expired_holds(self):
        ensure_site_settings()
        order = Order.objects.create(
            customer_name="Batch Expired User",
            customer_phone="07747055935",
            subtotal=Decimal("12.50"),
            total_amount=Decimal("12.50"),
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            requested_pickup_time=timezone.now() + timezone.timedelta(minutes=15),
        )
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get("/")
        payment = create_offline_pending_payment(order, request)
        payment.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        payment.save(update_fields=["expires_at"])

        expired_count = expire_due_offline_payments()

        self.assertEqual(expired_count, 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.EXPIRED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
