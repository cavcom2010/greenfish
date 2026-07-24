import json

from django.core.cache import cache
from django.test import Client, TestCase
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
        self.assertEqual(response.json()["start_url"], "/accounts/app/")
        shortcut_urls = {shortcut["url"] for shortcut in response.json()["shortcuts"]}
        self.assertIn("/menu/", shortcut_urls)
        self.assertIn("/rewards/", shortcut_urls)
        self.assertIn("/accounts/app/", shortcut_urls)

    def test_push_subscription_endpoints_validate_and_persist(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(reverse("account_login"))
        anonymous_csrf_token = csrf_client.cookies["csrftoken"].value

        invalid_response = csrf_client.post(
            reverse("pwa:subscribe_push"),
            data="{bad json",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=anonymous_csrf_token,
        )
        self.assertEqual(invalid_response.status_code, 400)

        csrf_client.force_login(self.user)
        csrf_client.get(reverse("accounts:profile"))
        csrf_token = csrf_client.cookies["csrftoken"].value
        payload = {
            "subscription": {
                "endpoint": "https://example.com/push/1",
                "keys": {"p256dh": "abc", "auth": "def"},
            },
            "device_name": "Test phone",
        }
        response = csrf_client.post(
            reverse("pwa:subscribe_push"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(endpoint=payload["subscription"]["endpoint"]).exists())

        unsubscribe = csrf_client.post(
            reverse("pwa:unsubscribe_push"),
            data=json.dumps({"endpoint": payload["subscription"]["endpoint"]}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(unsubscribe.status_code, 200)
        self.assertFalse(PushSubscription.objects.get(endpoint=payload["subscription"]["endpoint"]).is_active)

    def test_push_subscription_endpoints_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        payload = {
            "subscription": {
                "endpoint": "https://example.com/push/csrf",
                "keys": {"p256dh": "abc", "auth": "def"},
            }
        }

        response = csrf_client.post(
            reverse("pwa:subscribe_push"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_push_subscription_endpoint_is_rate_limited(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        csrf_client.get(reverse("accounts:profile"))
        csrf_token = csrf_client.cookies["csrftoken"].value

        for attempt in range(10):
            payload = {
                "subscription": {
                    "endpoint": f"https://example.com/push/{attempt}",
                    "keys": {"p256dh": "abc", "auth": "def"},
                }
            }
            response = csrf_client.post(
                reverse("pwa:subscribe_push"),
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertEqual(response.status_code, 200)

        blocked = csrf_client.post(
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
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_service_worker_caches_shell_and_excludes_sensitive_routes(self):
        response = self.client.get(reverse("pwa:service_worker"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("UNCACHEABLE_PREFIXES", body)
        self.assertIn("'/media/'", body)
        self.assertIn("'/payments/'", body)
        self.assertIn("'/ops/'", body)
        self.assertIn("'/accounts/app/'", body)
        self.assertIn("greenfish-", body)
        self.assertNotIn("clonedResponse", body)


class PushSendingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user(email="push@example.com")
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/sub/1",
            p256dh="p256dh-key",
            auth="auth-key",
        )

    def _order(self):
        from apps.core.test_support import create_order

        return create_order(user=self.user)

    def test_push_skipped_when_not_configured(self):
        from apps.pwa import services

        with self.settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY=""):
            self.assertFalse(services.push_configured())
            self.assertFalse(
                services.send_push_notification(self.subscription, "Title", "Body")
            )

    def test_push_sends_payload_with_vapid(self):
        from unittest.mock import patch

        from apps.pwa import services

        with self.settings(
            VAPID_PUBLIC_KEY="public",
            VAPID_PRIVATE_KEY="private",
            VAPID_ADMIN_EMAIL="shop@example.com",
        ):
            with patch.object(services, "webpush") as mock_webpush:
                ok = services.send_push_notification(
                    self.subscription, "Order Update", "Your order is ready"
                )

        self.assertTrue(ok)
        kwargs = mock_webpush.call_args.kwargs
        self.assertEqual(
            kwargs["subscription_info"]["endpoint"], self.subscription.endpoint
        )
        self.assertEqual(kwargs["vapid_claims"], {"sub": "mailto:shop@example.com"})
        payload = json.loads(kwargs["data"])
        self.assertEqual(payload["title"], "Order Update")

    def test_dead_subscription_deactivated_on_410(self):
        from unittest.mock import MagicMock, patch

        from pywebpush import WebPushException

        from apps.pwa import services

        response = MagicMock()
        response.status_code = 410
        exc = WebPushException("Gone", response=response)

        with self.settings(VAPID_PUBLIC_KEY="public", VAPID_PRIVATE_KEY="private"):
            with patch.object(services, "webpush", side_effect=exc):
                ok = services.send_push_notification(self.subscription, "T", "B")

        self.assertFalse(ok)
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.is_active)

    def test_notify_order_status_sends_to_active_subscriptions_only(self):
        from unittest.mock import patch

        from apps.pwa import services

        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.com/sub/2",
            p256dh="k",
            auth="a",
            is_active=False,
        )

        with self.settings(VAPID_PUBLIC_KEY="public", VAPID_PRIVATE_KEY="private"):
            with patch.object(services, "webpush") as mock_webpush:
                services.notify_order_status(self._order(), "Ready!")

        self.assertEqual(mock_webpush.call_count, 1)

    def test_vapid_public_key_exposed_to_templates(self):
        with self.settings(VAPID_PUBLIC_KEY="test-public-key"):
            response = self.client.get(reverse("core:home"))
        self.assertContains(response, "test-public-key")
