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
    path("orders/kanban/", views.kanban_board, name="kanban_board"),
    path("orders/kanban/column/<str:status>/", views.kanban_column_fragment, name="kanban_column"),
    path("orders/kanban/columns/", views.kanban_all_orders, name="kanban_columns"),
]
