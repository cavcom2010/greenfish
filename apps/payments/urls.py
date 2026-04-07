"""
URL patterns for the payments app.
"""
from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("create/", views.create_payment, name="create"),
    path("demo/<str:order_number>/", views.demo_checkout, name="demo_checkout"),
    path("return/<str:order_number>/", views.payment_return, name="return"),
    path("webhook/", views.webhook, name="webhook"),
    path("status/<str:order_number>/", views.payment_status_api, name="status"),
]
