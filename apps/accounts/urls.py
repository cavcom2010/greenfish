"""
URL patterns for the accounts app.
"""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("app/", views.app_home, name="app_home"),
    path("profile/", views.profile, name="profile"),
    path("my-orders/", views.order_history, name="order_history"),
    path("my-orders/claim/<str:order_number>/", views.claim_guest_order, name="claim_guest_order"),
    path("my-orders/<int:order_id>/reorder/", views.reorder, name="reorder"),
    path("favorites/<int:item_id>/add/", views.add_favorite_to_cart, name="add_favorite_to_cart"),
    path("favorites/<int:item_id>/toggle/", views.toggle_favorite, name="toggle_favorite"),
    path("saved-meals/<int:saved_meal_id>/add/", views.add_saved_meal_to_cart, name="add_saved_meal_to_cart"),
    path("saved-meals/order-item/<int:order_item_id>/save/", views.save_order_item_meal, name="save_order_item_meal"),
    # Override allauth auth pages with desktop-aware views
    path("login/", views.desktop_aware_login, name="account_login"),
    path("signup/", views.desktop_aware_signup, name="account_signup"),
    path("logout/", views.desktop_aware_logout, name="account_logout"),
    path("password/reset/", views.desktop_aware_password_reset, name="account_reset_password"),
    path("password/reset/done/", views.desktop_aware_password_reset_done, name="account_reset_password_done"),
    path(
        "password/reset/key/<uidb36>-<key>/",
        views.desktop_aware_password_reset_from_key,
        name="account_reset_password_from_key",
    ),
    path(
        "password/reset/key/done/",
        views.desktop_aware_password_reset_from_key_done,
        name="account_reset_password_from_key_done",
    ),
]
