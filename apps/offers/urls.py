"""
URL patterns for the offers app.
"""
from django.urls import path

from . import views

app_name = "offers"

urlpatterns = [
    path("", views.offer_list, name="list"),
    path("clear/", views.clear_offer, name="clear"),
    path("<int:pk>/activate/", views.activate_offer, name="activate"),
    path("<int:pk>/", views.offer_detail, name="detail"),
]
