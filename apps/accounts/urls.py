"""
URL patterns for the accounts app.
"""
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("my-orders/", views.order_history, name="order_history"),
]
