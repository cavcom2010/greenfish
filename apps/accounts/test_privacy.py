from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CustomerDataRequest
from apps.accounts.privacy import process_customer_data_request
from apps.core.test_support import create_order, create_user, ensure_site_settings
from apps.orders.models import Order


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

    def test_anonymisation_request_clears_order_personal_data(self):
        user = create_user(email="privacy-anon@example.com")
        order = create_order(
            user=user,
            customer_email=user.email,
            customer_phone="07747055935",
            delivery_address_line1="1 Private Road",
            delivery_city="Leeds",
            delivery_postcode="LS1 1AA",
            special_instructions="Leave by the blue door.",
        )
        data_request = CustomerDataRequest.objects.create(
            user=user,
            email=user.email,
            request_type=CustomerDataRequest.RequestType.ANONYMISATION,
        )

        process_customer_data_request(data_request)

        order.refresh_from_db()
        self.assertEqual(order.customer_name, "Anonymised Customer")
        self.assertEqual(order.customer_phone, "")
        self.assertEqual(order.delivery_address_line1, "")
        self.assertEqual(order.special_instructions, "")
        self.assertIsNone(order.user)
        self.assertIsNotNone(order.personal_data_anonymised_at)

    def test_retention_command_dry_run_does_not_change_orders(self):
        ensure_site_settings(order_personal_data_retention_years=6)
        order = create_order(customer_email="old-private@example.com", delivery_address_line1="Old Street")
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timezone.timedelta(days=7 * 365))
        out = StringIO()

        call_command("anonymise_old_order_personal_data", stdout=out)

        order.refresh_from_db()
        self.assertIn("Dry run: 1 order(s)", out.getvalue())
        self.assertEqual(order.customer_email, "old-private@example.com")
        self.assertIsNone(order.personal_data_anonymised_at)

    def test_retention_command_apply_anonymises_old_orders(self):
        ensure_site_settings(order_personal_data_retention_years=6)
        order = create_order(
            user=create_user(email="old-account@example.com"),
            customer_email="old-private@example.com",
            customer_phone="07747055935",
            delivery_address_line1="Old Street",
            special_instructions="Old note",
        )
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timezone.timedelta(days=7 * 365))
        out = StringIO()

        call_command("anonymise_old_order_personal_data", "--apply", stdout=out)

        order.refresh_from_db()
        self.assertIn("Anonymised 1 order(s)", out.getvalue())
        self.assertEqual(order.customer_name, "Anonymised Customer")
        self.assertEqual(order.customer_phone, "")
        self.assertEqual(order.delivery_address_line1, "")
        self.assertEqual(order.special_instructions, "")
        self.assertIsNone(order.user)
        self.assertIsNotNone(order.personal_data_anonymised_at)
