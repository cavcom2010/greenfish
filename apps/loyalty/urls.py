"""URL patterns for loyalty app."""
from django.urls import path

from . import views

app_name = "loyalty"

urlpatterns = [
    path("rewards/", views.rewards_dashboard, name="dashboard"),
    path("rewards/transactions/", views.transaction_history, name="transactions"),
    path("rewards/refer/", views.refer_friend, name="refer"),
    path("rewards/wallet/<int:pk>/activate/", views.activate_wallet_item, name="activate_wallet_item"),
    path("rewards/wallet/clear/", views.clear_wallet_item, name="clear_wallet_item"),
]
