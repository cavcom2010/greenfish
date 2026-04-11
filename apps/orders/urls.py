"""
URL patterns for the orders app.
"""
from django.urls import path

from . import views, views_kanban

app_name = "orders"

urlpatterns = [
    # Customer URLs
    path("cart/", views.cart_view, name="cart"),
    path("cart/drawer/", views.cart_drawer, name="cart_drawer"),
    path("cart/add/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<str:item_id>/", views.update_cart_item, name="update_cart_item"),
    path("cart/remove/<str:item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("service-type/", views.set_service_type, name="set_service_type"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/pay-instore/", views.pay_instore, name="pay_instore"),
    path("checkout/voucher/", views.apply_voucher, name="apply_voucher"),
    path("confirmation/<str:order_number>/", views.order_confirmation, name="confirmation"),
    path("confirmation/<str:order_number>/instore/", views.confirmation_instore, name="confirmation_instore"),
    path("track/<str:order_number>/", views.order_tracking, name="tracking"),
    
    # Dashboard URLs (Legacy List View)
    path("dashboard/", views.order_board, name="order_board"),
    path("dashboard/orders/fragment/", views.order_list_fragment, name="order_list_fragment"),
    path("dashboard/orders/<int:order_id>/update/", views.update_order_status, name="update_order_status"),
    path("dashboard/orders/<int:order_id>/detail/", views.order_detail_modal, name="order_detail_modal"),
    
    # Kanban Board URLs (New)
    path("kanban/", views_kanban.kanban_board, name="kanban_board"),
    path("kanban/column/<str:status>/", views_kanban.kanban_column_fragment, name="kanban_column"),
    path("kanban/update/<int:order_id>/", views_kanban.kanban_update_status, name="kanban_update"),
]
