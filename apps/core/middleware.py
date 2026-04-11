"""
Desktop detection middleware.

Determines whether the current request should be served the desktop or
mobile/PWA experience.  Detection order:
  1. Explicit ``view_mode`` cookie (``desktop`` or ``mobile``).
  2. User-Agent sniffing for known mobile patterns.
  3. Default → desktop (we want the full desktop site for ambiguous agents).

Adds ``request.is_desktop`` (bool) and a ``is_desktop`` template context
variable.
"""

import re

# Common mobile device patterns
_MOBILE_UA_PATTERNS = re.compile(
    r"Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini",
    re.IGNORECASE,
)


class DesktopDetectionMiddleware:
    """Attach ``request.is_desktop`` based on client hints."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Check explicit cookie
        view_mode_cookie = request.COOKIES.get("view_mode", "").lower()
        if view_mode_cookie == "desktop":
            request.is_desktop = True
            return self.get_response(request)
        if view_mode_cookie == "mobile":
            request.is_desktop = False
            return self.get_response(request)

        # 2. User-Agent sniffing
        ua = request.META.get("HTTP_USER_AGENT", "")
        request.is_desktop = not bool(_MOBILE_UA_PATTERNS.search(ua))

        return self.get_response(request)
