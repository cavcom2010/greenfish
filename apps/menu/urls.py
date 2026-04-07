"""
URL patterns for the menu app.
"""
from django.shortcuts import redirect
from django.urls import path

from . import views

app_name = "menu"

urlpatterns = [
    # Redirect old menu page to homepage (now merged)
    path("", lambda request: redirect('core:home', permanent=True), name="menu"),
    path("item/<int:pk>/", views.menu_item_detail, name="item_detail"),
    path("category/<int:category_id>/items/", views.category_items, name="category_items"),
]
