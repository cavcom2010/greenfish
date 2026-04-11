"""
URL patterns for the accounts app.
"""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("my-orders/", views.order_history, name="order_history"),
    # Override allauth auth pages with desktop-aware views
    path("login/", views.desktop_aware_login, name="account_login"),
    path("signup/", views.desktop_aware_signup, name="account_signup"),
    path("logout/", views.desktop_aware_logout, name="account_logout"),
    path("password/reset/", views.desktop_aware_password_reset, name="account_reset_password"),
]
