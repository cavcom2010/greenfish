"""
URL patterns for the analytics app.
"""
from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("sales/", views.sales_report, name="sales"),
    path("sales/export/", views.sales_export, name="sales_export"),
]
