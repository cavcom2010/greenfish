"""
URL configuration for Tinashe Takeaway project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("apps.accounts.urls", namespace="accounts")),
    path("", include("apps.core.urls", namespace="core")),
    path("menu/", include("apps.menu.urls", namespace="menu")),
    path("orders/", include("apps.orders.urls", namespace="orders")),
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
