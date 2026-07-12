"""
URL patterns for the offers app.
"""
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "offers"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="loyalty:dashboard", permanent=False), name="list"),
    path("clear/", views.clear_offer, name="clear"),
    path("<int:pk>/activate/", views.activate_offer, name="activate"),
    path("<int:pk>/", views.offer_detail, name="detail"),
]
