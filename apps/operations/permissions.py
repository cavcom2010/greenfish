from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect, render

OPERATIONS_MANAGER_GROUP = "Operations Manager"
OPERATIONS_KITCHEN_GROUP = "Operations Kitchen"
OPERATIONS_CASHIER_GROUP = "Operations Cashier"
OPERATIONS_DRIVER_GROUP = "Operations Driver"

ROLE_MANAGER = "manager"
ROLE_KITCHEN = "kitchen"
ROLE_CASHIER = "cashier"
ROLE_DRIVER = "driver"

BOARD_COLLECTION = "collection"
BOARD_KITCHEN = "kitchen"
BOARD_DRIVER = "driver"


def get_operations_roles(user):
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_staff", False):
        return set()

    group_names = set(
        user.groups.filter(
            name__in=[
                OPERATIONS_MANAGER_GROUP,
                OPERATIONS_KITCHEN_GROUP,
                OPERATIONS_CASHIER_GROUP,
                OPERATIONS_DRIVER_GROUP,
            ]
        ).values_list("name", flat=True)
    )

    roles = set()
    if OPERATIONS_MANAGER_GROUP in group_names:
        roles.add(ROLE_MANAGER)
    if OPERATIONS_KITCHEN_GROUP in group_names:
        roles.add(ROLE_KITCHEN)
    if OPERATIONS_CASHIER_GROUP in group_names:
        roles.add(ROLE_CASHIER)
    if OPERATIONS_DRIVER_GROUP in group_names:
        roles.add(ROLE_DRIVER)

    return roles


def has_operations_role(user, *roles):
    return bool(get_operations_roles(user).intersection(roles))


def is_operations_staff(user):
    """Back-office staff only. Drivers are deliberately excluded so the
    driver role never unlocks order_action/order_detail_modal or the
    kitchen/collection boards — drivers get their own gated endpoints."""
    return bool(get_operations_roles(user) - {ROLE_DRIVER})


def is_delivery_driver(user):
    return ROLE_DRIVER in get_operations_roles(user)


def can_access_board(user, board):
    roles = get_operations_roles(user)
    if ROLE_MANAGER in roles:
        return True
    if board == BOARD_KITCHEN:
        return ROLE_KITCHEN in roles
    if board == BOARD_COLLECTION:
        return ROLE_CASHIER in roles
    if board == BOARD_DRIVER:
        return ROLE_DRIVER in roles
    return False


def _driver_owns_order(user, order):
    """True when the order sits in a dispatched run belonging to this user's
    linked driver record."""
    run_order = getattr(order, "delivery_run_order", None)
    run = getattr(run_order, "run", None)
    driver = getattr(run, "driver", None)
    return (
        driver is not None
        and driver.user_id == user.id
        and run.status == run.Status.DISPATCHED
    )


def can_perform_action(user, action, order=None):
    roles = get_operations_roles(user)
    if ROLE_MANAGER in roles:
        return True

    kitchen_actions = {"accept_order", "start_preparing", "mark_ready", "save_notes"}
    cashier_actions = {"mark_paid", "mark_dispatched", "mark_collected", "mark_delivered", "save_notes"}

    if ROLE_KITCHEN in roles and action in kitchen_actions:
        return True
    if ROLE_CASHIER in roles and action in cashier_actions:
        return True
    if (
        ROLE_DRIVER in roles
        and action == "mark_delivered"
        and order is not None
        and _driver_owns_order(user, order)
    ):
        return True
    return False


def operations_board_required(board, json_response=False, redirect_name="core:home"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if can_access_board(request.user, board):
                return view_func(request, *args, **kwargs)
            if json_response:
                return JsonResponse({"error": "Unauthorized"}, status=403)
            if request.headers.get("HX-Request"):
                return render(request, "operations/orders/unauthorized.html", status=403)
            return redirect(redirect_name)

        return wrapped

    return decorator


def operations_staff_required(json_response=False, redirect_name="core:home"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if is_operations_staff(request.user):
                return view_func(request, *args, **kwargs)
            if json_response:
                return JsonResponse({"error": "Unauthorized"}, status=403)
            if request.headers.get("HX-Request"):
                return render(request, "operations/orders/unauthorized.html", status=403)
            return redirect(redirect_name)

        return wrapped

    return decorator
