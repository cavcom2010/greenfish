from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.test_support import create_order
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.services import MolliePaymentService


class MollieRefundPaymentTests(TestCase):
    def _make_payment(self):
        order = create_order(payment_status=Order.PaymentStatus.PAID)
        return Payment.objects.create(
            order=order,
            provider=Payment.Provider.MOLLIE,
            external_payment_id="tr_test123",
            mollie_payment_id="tr_test123",
            amount=Decimal("12.50"),
            currency="GBP",
            status=Payment.Status.PAID,
        )

    @patch("apps.payments.services.Client")
    def test_refund_payment_uses_payments_get_refunds_create(self, mock_client_class):
        """MolliePaymentService.refund_payment must use the mollie-api-python 4.x
        `client.payments.get(id).refunds.create(data)` chain. The old
        `client.payment_refunds.with_parent_id(id).create(data)` call does not
        exist on the installed client and raises AttributeError."""
        payment = self._make_payment()
        mock_client = mock_client_class.return_value
        mock_payment_resource = mock_client.payments.get.return_value

        service = MolliePaymentService()
        result = service.refund_payment(payment, amount=Decimal("5.00"))

        self.assertTrue(result)
        mock_client.payments.get.assert_called_once_with("tr_test123")
        mock_payment_resource.refunds.create.assert_called_once_with(
            {"amount": {"currency": "GBP", "value": "5.00"}}
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REFUNDED)

    @patch("apps.payments.services.Client")
    def test_refund_payment_full_amount_omits_amount_key(self, mock_client_class):
        payment = self._make_payment()
        mock_client = mock_client_class.return_value

        service = MolliePaymentService()
        service.refund_payment(payment, amount=None)

        mock_client.payments.get.return_value.refunds.create.assert_called_once_with({})
