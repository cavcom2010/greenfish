"""
URL patterns for the menu app.
"""
from django.urls import path

from . import views

app_name = "menu"

urlpatterns = [
    path("", views.menu_list, name="menu"),
    path("item/<int:pk>/", views.menu_item_detail, name="item_detail"),
    path("category/<int:category_id>/items/", views.category_items, name="category_items"),
]
