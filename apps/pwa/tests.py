import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_user, ensure_site_settings
from apps.pwa.models import PushSubscription


class PwaViewTests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_site_settings(shop_name="Two Fish PWA")
        self.user = create_user()

    def test_manifest_uses_site_settings(self):
        response = self.client.get(reverse("pwa:manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Two Fish PWA")

    def test_push_subscription_endpoints_validate_and_persist(self):
        invalid_response = self.client.post(
            reverse("pwa:subscribe_push"),
            data="{bad json",
            content_type="application/json",
        )
        self.assertEqual(invalid_response.status_code, 400)

        self.client.force_login(self.user)
        payload = {
            "subscription": {
                "endpoint": "https://example.com/push/1",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
            "device_name": "Test phone",
        }
        response = self.client.post(
            reverse("pwa:subscribe_push"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(endpoint=payload["subscription"]["endpoint"]).exists())

        unsubscribe = self.client.post(
            reverse("pwa:unsubscribe_push"),
            data=json.dumps({"endpoint": payload["subscription"]["endpoint"]}),
            content_type="application/json",
        )
        self.assertEqual(unsubscribe.status_code, 200)
        self.assertFalse(PushSubscription.objects.get(endpoint=payload["subscription"]["endpoint"]).is_active)

    def test_push_subscription_endpoint_is_rate_limited(self):
        self.client.force_login(self.user)

        for attempt in range(10):
            payload = {
                "subscription": {
                    "endpoint": f"https://example.com/push/{attempt}",
                    "keys": {"p256dh": "abc", "auth": "def"},
                }
            }
            response = self.client.post(
                reverse("pwa:subscribe_push"),
                data=json.dumps(payload),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(
            reverse("pwa:subscribe_push"),
            data=json.dumps(
                {
                    "subscription": {
                        "endpoint": "https://example.com/push/blocked",
                        "keys": {"p256dh": "abc", "auth": "def"},
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_service_worker_only_caches_static_shell_routes(self):
        response = self.client.get(reverse("pwa:service_worker"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("UNCACHEABLE_PREFIXES", body)
        self.assertIn("'/media/'", body)
        self.assertIn("'/payments/'", body)
        self.assertNotIn("cache.put(event.request, clonedResponse)", body)
