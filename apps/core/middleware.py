"""
Desktop detection middleware.

Determines whether the current request should be served the desktop or
mobile/PWA experience.  Detection order:
  1. Explicit ``view_mode`` cookie (``desktop`` or ``mobile``).
  2. ``Sec-CH-UA-Mobile`` client hint when present.
  3. User-Agent sniffing for known phone patterns.
  4. Default → desktop/tablet.

Adds ``request.is_desktop`` (bool) and a ``is_desktop`` template context
variable.
"""

import re

# Phone-class devices should get the mobile/PWA shell. Tablets should get the
# responsive desktop/tablet layout so they use the full viewport.
_PHONE_UA_PATTERNS = re.compile(
    r"iPhone|iPod|BlackBerry|IEMobile|Opera Mini|webOS",
    re.IGNORECASE,
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
