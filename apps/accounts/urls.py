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
    path("privacy/", views.privacy_center, name="privacy_center"),
    path("privacy/request/", views.create_data_request, name="create_data_request"),
    path("privacy/export/<int:request_id>/download/", views.download_data_export, name="download_data_export"),
    # Auth pages are handled by allauth's own views, which render the
    # unified templates in templates/account/.
]
