from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_order, create_user, ensure_site_settings
from apps.orders.models import OrderIssue


class CustomerOrderIssueTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="issue@example.com")
        self.order = create_order(user=self.user)

    def test_customer_can_report_issue_for_own_order(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("orders:create_issue", args=[self.order.order_number]),
            {
                "issue_type": OrderIssue.IssueType.MISSING_ITEM,
                "description": "The chips were missing from the order.",
                "requested_refund_amount": "3.50",
            },
        )

        self.assertEqual(response.status_code, 302)
        issue = OrderIssue.objects.get(order=self.order)
        self.assertEqual(issue.user, self.user)
        self.assertEqual(issue.requested_refund_amount, Decimal("3.50"))

    def test_guest_with_order_token_can_report_issue(self):
        guest_order = create_order(user=None)
        issue_url = f"{reverse('orders:create_issue', args=[guest_order.order_number])}?t={guest_order.public_access_token}"

        response = self.client.post(
            issue_url,
            {
                "issue_type": OrderIssue.IssueType.LATE_DELIVERY,
                "description": "The delivery is much later than expected.",
            },
        )

        self.assertEqual(response.status_code, 302)
        issue = OrderIssue.objects.get(order=guest_order)
        self.assertIsNone(issue.user)
        self.assertIn(guest_order.public_access_token, response.url)

    def test_customer_cannot_report_issue_for_someone_elses_order(self):
        other_user = create_user(email="other-issue@example.com")
        self.client.force_login(other_user)

        response = self.client.get(reverse("orders:create_issue", args=[self.order.order_number]))

        self.assertEqual(response.status_code, 404)

    def test_anonymous_without_order_token_cannot_report_issue(self):
        response = self.client.get(reverse("orders:create_issue", args=[self.order.order_number]))

        self.assertEqual(response.status_code, 404)

    def test_tracking_page_links_to_issue_flow(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("orders:tracking", args=[self.order.order_number]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("orders:create_issue", args=[self.order.order_number]))
        self.assertContains(response, f"t={self.order.public_access_token}")
