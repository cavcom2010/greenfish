"""
URL configuration for Tinashe Takeaway project.
"""
import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404
from django.templatetags.static import static as static_url
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=static_url("icons/icon-192.png"), permanent=True)),
    path(settings.ADMIN_URL_PREFIX, admin.site.urls),
    # Desktop-aware auth pages (must come before allauth to override)
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.core.urls", namespace="core")),
    path("menu/", include("apps.menu.urls", namespace="menu")),
    path("orders/", include("apps.orders.urls", namespace="orders")),
    path("ops/", include("apps.operations.urls", namespace="operations")),
    path("offers/", include("apps.offers.urls", namespace="offers")),
    path("payments/", include("apps.payments.urls", namespace="payments")),
    path("pwa/", include("apps.pwa.urls", namespace="pwa")),
    path("", include("apps.loyalty.urls", namespace="loyalty")),
    path("", include("apps.mealdeals.urls", namespace="mealdeals")),
    path("analytics/", include("apps.analytics.urls", namespace="analytics")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if not settings.DEBUG and getattr(settings, "DJANGO_SERVE_MEDIA", False):
    ALLOWED_MEDIA_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
        ".ico", ".pdf", ".css", ".js", ".json", ".xml",
        ".mp4", ".webm", ".woff", ".woff2",
    }

    def _media_serve_view(request, path):
        if not re.match(r"^[a-zA-Z0-9_\-./]+$", path):
            raise Http404
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if f".{ext}" not in ALLOWED_MEDIA_EXTENSIONS:
            raise Http404
        return serve(request, path, document_root=settings.MEDIA_ROOT)

    urlpatterns.insert(0, re_path(
        rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$",
        _media_serve_view,
        name="media_serve",
    ))
