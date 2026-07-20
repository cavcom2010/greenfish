"""
Staff-facing operations boards and actions.
"""
import logging

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.core.rate_limits import rate_limit
from apps.orders.models import Order

logger = logging.getLogger(__name__)

from .permissions import (
    BOARD_COLLECTION,
    BOARD_KITCHEN,
    can_access_board,
    get_operations_roles,
    operations_board_required,
    operations_staff_required,
)
from .services import (
    action_from_legacy_status,
    available_actions,
    get_all_kanban_columns,
    get_board_counts,
    get_collection_orders,
    get_kanban_orders,
    perform_order_action,
)


def _counts_context():
    counts = get_board_counts()
    return {
        "pending_count": counts["pending_count"],
        "confirmed_count": counts["confirmed_count"],
        "preparing_count": counts["preparing_count"],
        "ready_count": counts["ready_count"],
        "out_for_delivery_count": counts["out_for_delivery_count"],
        "collection_count": counts["collection_count"],
        "awaiting_payment_count": counts["awaiting_payment_count"],
        "kanban_confirmed_count": counts["kanban_confirmed_count"],
    }


def _board_nav_context(request):
    return {
        "can_access_collection_board": can_access_board(request.user, BOARD_COLLECTION),
        "can_access_kitchen_board": can_access_board(request.user, BOARD_KITCHEN),
        "operations_roles": sorted(get_operations_roles(request.user)),
    }


@operations_board_required(BOARD_COLLECTION)
def collection_board(request):
    context = {
        "orders": get_collection_orders(request.GET.get("status", ""), user=request.user),
        "board_mode": BOARD_COLLECTION,
        **_counts_context(),
        **_board_nav_context(request),
    }
    return render(request, "operations/orders/board.html", context)


@operations_board_required(BOARD_COLLECTION)
def order_board(request):
    return collection_board(request)


@operations_board_required(BOARD_COLLECTION, json_response=True)
def collection_list_fragment(request):
    return render(
        request,
        "operations/orders/_order_list.html",
        {
            "orders": get_collection_orders(request.GET.get("status", ""), user=request.user),
            "board_mode": BOARD_COLLECTION,
        },
    )


@operations_board_required(BOARD_COLLECTION, json_response=True)
def order_list_fragment(request):
    return collection_list_fragment(request)


@operations_staff_required(json_response=True)
def order_detail_modal(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("user", "payment", "payment__manual_receipt").prefetch_related("items"),
        pk=order_id,
    )
    order.available_actions = available_actions(order, user=request.user)
    return render(
        request,
        "operations/orders/_order_detail.html",
        {"order": order},
    )


@operations_staff_required(json_response=True)
@require_POST
@rate_limit("ops-order-action", limit=60, window_seconds=60)
def order_action(request, order_id):
    action = (request.POST.get("action") or "").strip()
    expected_status = (request.POST.get("expected_status") or "").strip()

    try:
        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update().select_related("user", "payment").prefetch_related("items"),
                pk=order_id,
            )
            if expected_status and order.status != expected_status:
                return JsonResponse(
                    {"error": "Order changed. Refresh the board and try again."},
                    status=409,
                )

            if not action:
                action = action_from_legacy_status(order, request.POST.get("status"))
            if not action:
                return JsonResponse({"error": "Invalid action"}, status=400)

            order = perform_order_action(
                order,
                action,
                request.user,
                staff_notes=request.POST.get("staff_notes", ""),
                handover_notes=request.POST.get("handover_notes", ""),
                cancel_reason=request.POST.get("cancel_reason", ""),
                payment_method=request.POST.get("payment_method", ""),
                payment_amount_received=request.POST.get("payment_amount_received", ""),
                payment_reference_code=request.POST.get("payment_reference_code", ""),
                payment_notes=request.POST.get("payment_notes", ""),
                request=request,
            )

        order.available_actions = available_actions(order, user=request.user)

        if request.headers.get("HX-Request"):
            template_name = (
                "operations/orders/kanban_card.html"
                if request.POST.get("view") == "kanban"
                else "operations/orders/_order_card.html"
            )
            return render(request, template_name, {"order": order})

        return JsonResponse({"success": True, "order_id": order_id, "status": order.status, "action": action})

    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except ValidationError as exc:
        message = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"error": message}, status=400)
    except DatabaseError as exc:
        logger.exception("Database error performing %s on order %s", action, order_id)
        return JsonResponse(
            {"error": "A conflict occurred. Refresh the board and try again."},
            status=409,
        )
    except Exception:
        logger.exception("Unexpected error performing %s on order %s", action, order_id)
        return JsonResponse(
            {"error": "Something went wrong. Please try again."},
            status=500,
        )


@operations_board_required(BOARD_KITCHEN)
def kitchen_board(request):
    context = {
        **_counts_context(),
        **_board_nav_context(request),
        "title": "Kitchen Board",
    }
    return render(request, "operations/orders/kanban_board.html", context)


@operations_board_required(BOARD_KITCHEN)
def kanban_board(request):
    return kitchen_board(request)


@operations_board_required(BOARD_KITCHEN, json_response=True)
def kanban_column_fragment(request, status):
    return render(
        request,
        "operations/orders/kanban_column.html",
        {
            "orders": get_kanban_orders(status, user=request.user),
            "column_status": status,
        },
    )


@operations_board_required(BOARD_KITCHEN, json_response=True)
def kanban_all_orders(request):
    return render(
        request,
        "operations/orders/kanban_columns.html",
        {"columns": get_all_kanban_columns(user=request.user)},
    )
