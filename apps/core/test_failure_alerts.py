from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.core.middleware import FailureAlertMiddleware


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ADMIN_EMAIL="alerts@example.com",
    SHOP_EMAIL="shop@example.com",
    DEFAULT_FROM_EMAIL="orders@example.com",
    SERVER_EMAIL="server@example.com",
    ADMIN_FAILURE_ALERTS_ENABLED=True,
    ADMIN_FAILURE_ALERT_THROTTLE_SECONDS=600,
)
class FailureAlertMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory(HTTP_HOST="greenfish.test")

    def _request(self, path="/accounts/login/", method="post", **extra):
        request_method = getattr(self.factory, method)
        request = request_method(path, data={"password": "secret-password"}, **extra)
        request.user = AnonymousUser()
        return request

    def test_critical_403_sends_admin_email(self):
        middleware = FailureAlertMiddleware(lambda request: HttpResponse("Forbidden", status=403))

        response = middleware(self._request(HTTP_USER_AGENT="Mobile", HTTP_X_FORWARDED_FOR="198.51.100.10"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alerts@example.com"])
        self.assertEqual(mail.outbox[0].from_email, "server@example.com")
        self.assertIn("[GreenFish] 403 on POST /accounts/login/", mail.outbox[0].subject)
        self.assertIn("Client IP: 198.51.100.10", mail.outbox[0].body)
        self.assertNotIn("secret-password", mail.outbox[0].body)

    def test_500_exception_sends_admin_email_and_reraises(self):
        def broken_view(request):
            raise RuntimeError("database unavailable")

        middleware = FailureAlertMiddleware(broken_view)

        with self.assertRaisesMessage(RuntimeError, "database unavailable"):
            middleware(self._request("/menu/", method="get"))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("[GreenFish] 500 on GET /menu/", mail.outbox[0].subject)
        self.assertIn("RuntimeError", mail.outbox[0].body)

    @override_settings(ALLOWED_HOSTS=["greenfish.test"])
    def test_alert_message_handles_invalid_host_metadata(self):
        middleware = FailureAlertMiddleware(lambda request: HttpResponse("Broken", status=500))

        response = middleware(self._request("/menu/", method="get", HTTP_HOST="bad host\r\nInjected: yes"))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Host: bad hostInjected: yes", mail.outbox[0].body)

    def test_unimportant_statuses_do_not_send_email(self):
        for status_code, path in [
            (404, "/missing/"),
            (429, "/accounts/login/"),
            (403, "/favicon.ico"),
            (403, "/.well-known/assetlinks.json"),
            (302, "/accounts/login/"),
        ]:
            with self.subTest(status_code=status_code, path=path):
                middleware = FailureAlertMiddleware(lambda request, status_code=status_code: HttpResponse(status=status_code))
                middleware(self._request(path, method="get"))

        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_alerts_are_throttled(self):
        middleware = FailureAlertMiddleware(lambda request: HttpResponse("Forbidden", status=403))

        middleware(self._request())
        middleware(self._request())

        self.assertEqual(len(mail.outbox), 1)

    @override_settings(ADMIN_EMAIL="", SHOP_EMAIL="shop@example.com")
    def test_shop_email_is_fallback_recipient(self):
        middleware = FailureAlertMiddleware(lambda request: HttpResponse("Forbidden", status=403))

        middleware(self._request())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["shop@example.com"])

    @override_settings(ADMIN_FAILURE_ALERTS_ENABLED=False)
    def test_alerts_can_be_disabled(self):
        middleware = FailureAlertMiddleware(lambda request: HttpResponse("Forbidden", status=403))

        middleware(self._request())

        self.assertEqual(len(mail.outbox), 0)
