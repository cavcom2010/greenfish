"""
Kanban Order Board views for kitchen display.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import Order


@login_required
def kanban_board(request):
    """Compatibility route to the operations kanban board."""
    from apps.operations.views import kanban_board as operations_kanban_board

    return operations_kanban_board(request)


@login_required
def kanban_column_fragment(request, status):
    """Compatibility route to the operations kanban column fragment."""
    from apps.operations.views import kanban_column_fragment as operations_kanban_column_fragment

    return operations_kanban_column_fragment(request, status)


@login_required
@require_POST
def kanban_update_status(request, order_id):
    """Compatibility route to the operations action endpoint."""
    from apps.operations.views import order_action

    return order_action(request, order_id)


@login_required
def kanban_all_orders(request):
    """Compatibility route to all operations kanban columns."""
    from apps.operations.views import kanban_all_orders as operations_kanban_all_orders

    return operations_kanban_all_orders(request)
