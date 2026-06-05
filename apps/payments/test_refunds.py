from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import NotificationEvent
from apps.core.test_support import create_order
from apps.orders.models import Order
from apps.payments.models import Payment, RefundRequest
from apps.payments.services import process_refund_request


class RefundWorkflowTests(TestCase):
    @patch("apps.payments.services.payment_service_for_payment")
    def test_process_refund_request_updates_status(self, mocked_service_factory):
        order = create_order(payment_status=Order.PaymentStatus.PAID)
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.STRIPE,
            external_payment_id="cs_test_refund",
            amount=Decimal("12.50"),
            status=Payment.Status.PAID,
        )
        refund = RefundRequest.objects.create(payment=payment, amount=Decimal("5.00"), reason="Customer request")
        mocked_service_factory.return_value.refund_payment.return_value = True

        process_refund_request(refund)
        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundRequest.Status.SUCCEEDED)
        self.assertTrue(
            NotificationEvent.objects.filter(
                order=order,
                channel=NotificationEvent.Channel.EMAIL,
                event_type="order_refund_processed",
                recipient=order.customer_email,
            ).exists()
        )
