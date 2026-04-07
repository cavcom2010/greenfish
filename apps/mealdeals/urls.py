"""URL patterns for meal deals."""
from django.urls import path

from . import views

app_name = "mealdeals"

urlpatterns = [
    path("deals/", views.deal_list, name="list"),
    path("deals/<int:deal_id>/", views.deal_detail, name="detail"),
]
