"""
Kanban Order Board views for kitchen display.
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import Order


def kanban_board(request):
    """Kanban-style order board for kitchen staff."""
    if not request.user.is_staff:
        return render(request, "orders/dashboard/unauthorized.html")
    
    # Count orders by status
    confirmed_count = Order.objects.filter(
        status__in=[Order.Status.CONFIRMED, Order.Status.PENDING]
    ).count()
    preparing_count = Order.objects.filter(
        status=Order.Status.PREPARING
    ).count()
    ready_count = Order.objects.filter(
        status=Order.Status.READY
    ).count()
    
    context = {
        "confirmed_count": confirmed_count,
        "preparing_count": preparing_count,
        "ready_count": ready_count,
        "title": "Kitchen Board",
    }
    return render(request, "orders/dashboard/kanban_board.html", context)


def kanban_column_fragment(request, status):
    """Get orders for a specific Kanban column (HTMX)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    status_map = {
        "confirmed": [Order.Status.CONFIRMED, Order.Status.PENDING],
        "preparing": [Order.Status.PREPARING],
        "ready": [Order.Status.READY],
    }
    
    statuses = status_map.get(status, [Order.Status.CONFIRMED])
    orders = Order.objects.filter(
        status__in=statuses
    ).order_by("created_at")
    
    return render(request, "orders/dashboard/kanban_column.html", {
        "orders": orders,
        "column_status": status,
    })


@require_POST
def kanban_update_status(request, order_id):
    """Update order status (from drag-drop or button)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get("status")
    
    status_map = {
        "confirmed": Order.Status.CONFIRMED,
        "preparing": Order.Status.PREPARING,
        "ready": Order.Status.READY,
        "completed": Order.Status.COMPLETED,
    }
    
    if new_status in status_map:
        old_status = order.status
        order.status = status_map[new_status]
        order.save()
        
        # Send notifications when order is ready
        if new_status == "ready" and old_status != Order.Status.READY:
            try:
                from apps.sms.services import send_order_ready
                send_order_ready(order)
            except Exception:
                pass
            
            try:
                from apps.pwa.services import notify_order_ready
                notify_order_ready(order)
            except Exception:
                pass
        
        # Return updated card for HTMX swap
        if request.headers.get("HX-Request"):
            return render(request, "orders/dashboard/kanban_card.html", {"order": order})
        
        return JsonResponse({"success": True, "order_id": order_id, "status": new_status})
    
    return JsonResponse({"error": "Invalid status"}, status=400)


def kanban_all_orders(request):
    """Get all orders for all columns (for initial load)."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    columns = {
        "confirmed": Order.objects.filter(
            status__in=[Order.Status.CONFIRMED, Order.Status.PENDING]
        ).order_by("created_at"),
        "preparing": Order.objects.filter(
            status=Order.Status.PREPARING
        ).order_by("created_at"),
        "ready": Order.objects.filter(
            status=Order.Status.READY
        ).order_by("created_at"),
    }
    
    return render(request, "orders/dashboard/kanban_columns.html", {
        "columns": columns,
    })
