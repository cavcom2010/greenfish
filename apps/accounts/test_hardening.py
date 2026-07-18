"""Tests for self-service privacy, signup wiring, and endpoint rate limits."""
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomerDataRequest, User
from apps.core.test_support import create_user


class PrivacyCenterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user(email="privacy@example.com")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:privacy_center"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_page_renders(self):
        response = self.client.get(reverse("accounts:privacy_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Export my data")
        self.assertContains(response, "Delete my account data")

    def test_export_request_created(self):
        response = self.client.post(
            reverse("accounts:create_data_request"),
            {"request_type": "export"},
        )
        self.assertRedirects(response, reverse("accounts:privacy_center"))
        self.assertTrue(
            CustomerDataRequest.objects.filter(
                user=self.user,
                request_type=CustomerDataRequest.RequestType.EXPORT,
                status=CustomerDataRequest.Status.REQUESTED,
            ).exists()
        )

    def test_duplicate_open_request_blocked(self):
        self.client.post(reverse("accounts:create_data_request"), {"request_type": "export"})
        self.client.post(reverse("accounts:create_data_request"), {"request_type": "export"})
        self.assertEqual(
            CustomerDataRequest.objects.filter(user=self.user, request_type="export").count(),
            1,
        )

    def test_deletion_requires_typed_confirmation(self):
        response = self.client.post(
            reverse("accounts:create_data_request"),
            {"request_type": "anonymisation", "confirm": "nope"},
        )
        self.assertRedirects(response, reverse("accounts:privacy_center"))
        self.assertFalse(
            CustomerDataRequest.objects.filter(user=self.user, request_type="anonymisation").exists()
        )

        self.client.post(
            reverse("accounts:create_data_request"),
            {"request_type": "anonymisation", "confirm": "delete"},
        )
        self.assertTrue(
            CustomerDataRequest.objects.filter(user=self.user, request_type="anonymisation").exists()
        )

    def test_export_download_owner_only(self):
        data_request = CustomerDataRequest.objects.create(
            user=self.user,
            email=self.user.email,
            request_type=CustomerDataRequest.RequestType.EXPORT,
            status=CustomerDataRequest.Status.COMPLETED,
            export_payload={"user": {"email": self.user.email}},
        )

        response = self.client.get(
            reverse("accounts:download_data_export", args=[data_request.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

        other = create_user(email="other@example.com")
        self.client.force_login(other)
        response = self.client.get(
            reverse("accounts:download_data_export", args=[data_request.pk])
        )
        self.assertEqual(response.status_code, 404)


class SignupFormWiringTests(TestCase):
    def test_signup_collects_names_and_phone(self):
        response = self.client.get(reverse("account_signup"))
        self.assertContains(response, "first_name")
        self.assertContains(response, "last_name")

        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "newcustomer@example.com",
                "password1": "s3cure-pass-word!",
                "password2": "s3cure-pass-word!",
                "first_name": "New",
                "last_name": "Customer",
                "phone_number": "07700900000",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="newcustomer@example.com")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "Customer")
        self.assertEqual(user.phone_number, "07700900000")

    def test_signup_requires_names(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "incomplete@example.com",
                "password1": "s3cure-pass-word!",
                "password2": "s3cure-pass-word!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="incomplete@example.com").exists())


class PublicEndpointRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_newsletter_signup_rate_limited(self):
        url = reverse("core:newsletter")
        for _ in range(5):
            response = self.client.post(url, {"email": "spam@example.com"})
            self.assertNotEqual(response.status_code, 429)
        response = self.client.post(url, {"email": "spam@example.com"})
        self.assertEqual(response.status_code, 429)

    def test_large_order_request_rate_limited(self):
        url = reverse("core:large_orders")
        for _ in range(5):
            self.client.post(url, {})
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 429)


class RefundPermissionGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = create_user(email="staff@example.com", is_staff=True)
        for codename in ["view_refundrequest", "change_refundrequest"]:
            self.staff.user_permissions.add(Permission.objects.get(codename=codename))

    def test_staff_without_refund_permission_cannot_process(self):
        from decimal import Decimal

        from apps.core.test_support import create_order
        from apps.orders.models import Order
        from apps.payments.models import Payment, RefundRequest

        order = create_order(payment_status=Order.PaymentStatus.PAID)
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.STRIPE,
            external_payment_id="cs_perm",
            amount=Decimal("12.50"),
            currency="GBP",
            status=Payment.Status.PAID,
        )
        refund = RefundRequest.objects.create(payment=payment, reason="test")

        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin:payments_refundrequest_changelist"),
            {
                "action": "process_refunds",
                "_selected_action": [str(refund.pk)],
            },
        )

        refund.refresh_from_db()
        self.assertEqual(refund.status, RefundRequest.Status.REQUESTED)
