"""
URL patterns for the core app.
"""
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("large-orders/", views.large_order_request, name="large_orders"),
    path("newsletter/", views.newsletter_signup, name="newsletter"),
    path("cookie-consent/", views.record_cookie_consent, name="cookie_consent"),
]
