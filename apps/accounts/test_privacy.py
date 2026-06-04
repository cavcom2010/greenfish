from django.test import TestCase

from apps.accounts.models import CustomerDataRequest
from apps.accounts.privacy import process_customer_data_request
from apps.core.test_support import create_order, create_user


class CustomerDataRequestTests(TestCase):
    def test_export_request_collects_account_and_order_data(self):
        user = create_user(email="privacy@example.com")
        order = create_order(user=user, customer_email=user.email)
        data_request = CustomerDataRequest.objects.create(
            user=user,
            email=user.email,
            request_type=CustomerDataRequest.RequestType.EXPORT,
        )

        process_customer_data_request(data_request)
        data_request.refresh_from_db()
        self.assertEqual(data_request.status, CustomerDataRequest.Status.COMPLETED)
        self.assertEqual(data_request.export_payload["user"]["email"], user.email)
        self.assertEqual(data_request.export_payload["orders"][0]["order_number"], order.order_number)
