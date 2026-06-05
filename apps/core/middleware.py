"""Core middleware."""
import hashlib
import logging
import re
import traceback

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.core.mail import EmailMessage
from django.utils import timezone

from .request_meta import client_ip_from_request

logger = logging.getLogger(__name__)

# Phone-class devices should get the mobile/PWA shell. Tablets should get the
# responsive desktop/tablet layout so they use the full viewport.
_PHONE_UA_PATTERNS = re.compile(
    r"iPhone|iPod|BlackBerry|IEMobile|Opera Mini|webOS",
    re.IGNORECASE,
)
_IGNORED_ALERT_PREFIXES = (
    "/health/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/.well-known/",
)
_CRITICAL_ALERT_PREFIXES = (
    "/accounts/",
    "/admin/",
    "/orders/checkout/",
    "/payments/",
    "/ops/",
)


def should_use_desktop_layout(request):
    """Return True for desktop/tablet layouts and False for phone layouts."""
    view_mode_cookie = request.COOKIES.get("view_mode", "").lower()
    if view_mode_cookie == "desktop":
        return True
    if view_mode_cookie == "mobile":
        return False

    mobile_hint = request.META.get("HTTP_SEC_CH_UA_MOBILE", "").strip()
    if mobile_hint == "?1":
        return False

    ua = request.META.get("HTTP_USER_AGENT", "")
    if "Android" in ua:
        return "Mobile" not in ua
    if "iPad" in ua:
        return True

    if _PHONE_UA_PATTERNS.search(ua):
        return False
    if mobile_hint == "?0":
        return True
    return True


class DesktopDetectionMiddleware:
    """Attach ``request.is_desktop`` based on client hints."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.is_desktop = should_use_desktop_layout(request)
        return self.get_response(request)


def _exception_status(exc):
    if isinstance(exc, PermissionDenied):
        return 403
    if isinstance(exc, (BadRequest, SuspiciousOperation)):
        return 400
    return 500


def _is_important_failure(path, status_code):
    if any(path.startswith(prefix) for prefix in _IGNORED_ALERT_PREFIXES):
        return False
    if status_code >= 500:
        return True
    if status_code in {400, 403}:
        return any(path.startswith(prefix) for prefix in _CRITICAL_ALERT_PREFIXES)
    return False


def _admin_alert_recipient():
    return (getattr(settings, "ADMIN_EMAIL", "") or getattr(settings, "SHOP_EMAIL", "") or "").strip()


def _safe_meta_value(value):
    return str(value or "").replace("\r", "").replace("\n", "")[:500]


class FailureAlertMiddleware:
    """Email admins for important production failures without noisy false positives."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception as exc:
            self._send_alert(request, _exception_status(exc), exc=exc)
            raise

        status_code = getattr(response, "status_code", 200)
        if _is_important_failure(request.path, status_code):
            self._send_alert(request, status_code)
        return response

    def _send_alert(self, request, status_code, exc=None):
        if not getattr(settings, "ADMIN_FAILURE_ALERTS_ENABLED", True):
            return

        recipient = _admin_alert_recipient()
        if not recipient:
            return

        path = getattr(request, "path", "")
        if not _is_important_failure(path, status_code):
            return

        fingerprint = self._fingerprint(request, status_code, exc)
        throttle_seconds = max(1, int(getattr(settings, "ADMIN_FAILURE_ALERT_THROTTLE_SECONDS", 600)))
        cache_key = f"failure-alert:{fingerprint}"
        if cache.get(cache_key):
            return
        cache.set(cache_key, True, throttle_seconds)

        subject = f"[GreenFish] {status_code} on {request.method} {path}"
        message = self._message(request, status_code, exc)
        from_email = getattr(settings, "SERVER_EMAIL", "") or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        try:
            EmailMessage(subject=subject, body=message, from_email=from_email, to=[recipient]).send(
                fail_silently=False
            )
        except Exception:
            logger.exception("Failed to send admin failure alert")

    def _fingerprint(self, request, status_code, exc=None):
        parts = [
            str(status_code),
            request.method,
            getattr(request, "path", ""),
            exc.__class__.__name__ if exc else "",
            str(exc)[:160] if exc else "",
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def _message(self, request, status_code, exc=None):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            user_label = f"{user.pk} <{getattr(user, 'email', '')}>"
        else:
            user_label = "anonymous"

        lines = [
            "GreenFish important failure alert",
            "",
            f"Timestamp: {timezone.now().isoformat()}",
            f"Status: {status_code}",
            f"Method: {request.method}",
            f"Path: {request.get_full_path()}",
            f"Host: {_safe_meta_value(request.META.get('HTTP_HOST') or request.META.get('SERVER_NAME'))}",
            f"Client IP: {client_ip_from_request(request) or 'unknown'}",
            f"User: {user_label}",
            f"Referer: {_safe_meta_value(request.META.get('HTTP_REFERER'))}",
            f"User-Agent: {_safe_meta_value(request.META.get('HTTP_USER_AGENT'))}",
            f"Commit: {getattr(settings, 'RELEASE_COMMIT', '') or 'unknown'}",
        ]
        if exc:
            lines.extend(
                [
                    "",
                    f"Exception: {exc.__class__.__name__}",
                    f"Message: {str(exc)}",
                    "",
                    "Traceback:",
                    "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:6000],
                ]
            )
        return "\n".join(lines)
