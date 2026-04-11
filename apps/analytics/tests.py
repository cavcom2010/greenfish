from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_order, create_user, ensure_site_settings


class AnalyticsDashboardTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.staff_user = create_user(email="staff@example.com", is_staff=True)
        create_order(user=self.staff_user)

    def test_analytics_requires_staff_login(self):
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_analytics_dashboard_renders_for_staff(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analytics")
