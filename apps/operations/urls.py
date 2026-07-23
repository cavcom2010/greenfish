from django.urls import path

from . import views

app_name = "operations"

urlpatterns = [
    path("orders/collection/", views.collection_board, name="collection_board"),
    path("orders/collection/fragment/", views.collection_list_fragment, name="collection_list_fragment"),
    path("orders/kitchen/", views.kitchen_board, name="kitchen_board"),
    path("orders/board/", views.order_board, name="order_board"),
    path("orders/board/fragment/", views.order_list_fragment, name="order_list_fragment"),
    path("orders/<int:order_id>/detail/", views.order_detail_modal, name="order_detail_modal"),
    path("orders/<int:order_id>/action/", views.order_action, name="order_action"),
    path("orders/delivery/", views.delivery_panel, name="delivery_panel"),
    path("orders/delivery/fragment/", views.delivery_panel_fragment, name="delivery_panel_fragment"),
    path("orders/delivery/assign/", views.delivery_assign, name="delivery_assign"),
    path("orders/delivery/unassign/", views.delivery_unassign, name="delivery_unassign"),
    path("orders/delivery/runs/<int:run_id>/dispatch/", views.delivery_dispatch, name="delivery_dispatch"),
    path("driver/", views.driver_board, name="driver_board"),
    path("driver/fragment/", views.driver_board_fragment, name="driver_board_fragment"),
    path("driver/run/<int:run_id>/dispatch/", views.driver_dispatch, name="driver_dispatch"),
    path("driver/orders/<int:order_id>/delivered/", views.driver_order_delivered, name="driver_order_delivered"),
    path("orders/kanban/", views.kanban_board, name="kanban_board"),
    path("orders/kanban/column/<str:status>/", views.kanban_column_fragment, name="kanban_column"),
    path("orders/kanban/columns/", views.kanban_all_orders, name="kanban_columns"),
]
