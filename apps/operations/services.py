"""
Staff order-board workflow services.
"""
import logging

from django.db.models import Count, Prefetch

from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from .permissions import can_perform_action, get_operations_roles

logger = logging.getLogger(__name__)

KITCHEN_BOARD_STATUSES = (
    Order.OrderStatus.PENDING,
    Order.OrderStatus.CONFIRMED,
    Order.OrderStatus.PREPARING,
    Order.OrderStatus.READY,
)

COLLECTION_BOARD_STATUSES = (
    Order.OrderStatus.READY,
    Order.OrderStatus.OUT_FOR_DELIVERY,
)

KANBAN_COLUMNS = {
    "confirmed": (Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED),
    "preparing": (Order.OrderStatus.PREPARING,),
    "ready": (Order.OrderStatus.READY,),
}

ACTION_ACCEPT_ORDER = "accept_order"
ACTION_START_PREPARING = "start_preparing"
ACTION_MARK_READY = "mark_ready"
ACTION_MARK_DISPATCHED = "mark_dispatched"
ACTION_MARK_COLLECTED = "mark_collected"
ACTION_MARK_DELIVERED = "mark_delivered"
ACTION_CANCEL_ORDER = "cancel_order"
ACTION_MARK_PAID = "mark_paid"
ACTION_SAVE_NOTES = "save_notes"


def board_queryset():
    return (
        Order.objects.select_related("user")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.order_by("id")))
        .filter(payment_status=Order.PaymentStatus.PAID)
        .order_by("created_at")
    )


def awaiting_payment_queryset():
    return (
        Order.objects.select_related("user", "payment")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.order_by("id")))
        .filter(
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            payment__provider=Payment.Provider.OFFLINE_PENDING,
            payment__status=Payment.Status.PENDING,
        )
        .order_by("created_at")
    )


def kitchen_board_queryset():
    return board_queryset().filter(status__in=KITCHEN_BOARD_STATUSES)


def collection_board_queryset():
    return board_queryset().filter(status__in=COLLECTION_BOARD_STATUSES)


def get_board_counts():
    status_counts = dict(
        Order.objects.filter(payment_status=Order.PaymentStatus.PAID)
        .values_list("status")
        .annotate(count=Count("id"))
    )
    awaiting_payment_count = awaiting_payment_queryset().count()
    collection_count = sum(status_counts.get(status, 0) for status in COLLECTION_BOARD_STATUSES)
    kanban_confirmed_count = sum(status_counts.get(status, 0) for status in KANBAN_COLUMNS["confirmed"])
    return {
        "pending_count": status_counts.get(Order.OrderStatus.PENDING, 0),
        "confirmed_count": status_counts.get(Order.OrderStatus.CONFIRMED, 0),
        "preparing_count": status_counts.get(Order.OrderStatus.PREPARING, 0),
        "ready_count": status_counts.get(Order.OrderStatus.READY, 0),
        "out_for_delivery_count": status_counts.get(Order.OrderStatus.OUT_FOR_DELIVERY, 0),
        "awaiting_payment_count": awaiting_payment_count,
        "collection_count": collection_count + awaiting_payment_count,
        "kanban_confirmed_count": kanban_confirmed_count,
    }


def get_collection_orders(status_filter="", user=None):
    if status_filter == "awaiting_payment":
        return attach_available_actions(awaiting_payment_queryset()[:50], user=user)

    queryset = collection_board_queryset()
    if status_filter in {Order.OrderStatus.READY, Order.OrderStatus.OUT_FOR_DELIVERY}:
        queryset = queryset.filter(status=status_filter)
        return attach_available_actions(queryset[:50], user=user)

    paid_orders = list(queryset[:50])
    awaiting_orders = list(awaiting_payment_queryset()[:50])
    orders = sorted(awaiting_orders + paid_orders, key=lambda order: order.created_at)[:50]
    return attach_available_actions(orders, user=user)


def get_kanban_orders(column_status, user=None):
    statuses = KANBAN_COLUMNS.get(column_status, KANBAN_COLUMNS["confirmed"])
    return attach_available_actions(board_queryset().filter(status__in=statuses)[:50], user=user)


def get_all_kanban_columns(user=None):
    return {column: get_kanban_orders(column, user=user) for column in KANBAN_COLUMNS}


def attach_available_actions(orders, user=None):
    roles = get_operations_roles(user) if user else set()
    for order in orders:
        order.available_actions = _available_actions_cached(order, roles=roles)
    return orders


def available_actions(order, user=None):
    roles = get_operations_roles(user) if user else set()
    return _available_actions_cached(order, roles=roles)


def _available_actions_cached(order, *, roles):
    actions = _build_actions_for_order(order)
    if not roles:
        return actions
    return [_a for _a in actions if _action_permitted(_a["name"], roles)]


def _build_actions_for_order(order):
    available = []

    if order.status == Order.OrderStatus.PENDING:
        if order.payment_status == Order.PaymentStatus.PAID:
            available.append(_action(ACTION_ACCEPT_ORDER, "Accept Order", "btn-confirm"))
        elif getattr(order, "payment", None) and order.payment.provider == Payment.Provider.OFFLINE_PENDING:
            available.append(_action(ACTION_MARK_PAID, "Mark Paid", "btn-confirm"))

    elif order.status == Order.OrderStatus.CONFIRMED:
        available.append(_action(ACTION_START_PREPARING, "Start Preparing", "btn-preparing"))

    elif order.status == Order.OrderStatus.PREPARING:
        available.append(_action(ACTION_MARK_READY, "Mark Ready", "btn-ready"))

    elif order.status == Order.OrderStatus.READY:
        if order.is_delivery:
            available.append(_action(ACTION_MARK_DISPATCHED, "Mark Dispatched", "btn-dispatch"))
        else:
            available.append(_action(ACTION_MARK_COLLECTED, "Mark Collected", "btn-complete"))

    elif order.status == Order.OrderStatus.OUT_FOR_DELIVERY:
        available.append(_action(ACTION_MARK_DELIVERED, "Mark Delivered", "btn-complete"))

    if order.status not in {Order.OrderStatus.COMPLETED, Order.OrderStatus.CANCELLED}:
        available.append(_action(ACTION_CANCEL_ORDER, "Cancel Order", "btn-cancel"))

    return available


def _action_permitted(action_name, roles):
    from .permissions import ROLE_MANAGER, ROLE_KITCHEN, ROLE_CASHIER, ROLE_DRIVER

    if ROLE_MANAGER in roles:
        return True
    kitchen_actions = {ACTION_ACCEPT_ORDER, ACTION_START_PREPARING, ACTION_MARK_READY, ACTION_SAVE_NOTES}
    cashier_actions = {ACTION_MARK_PAID, ACTION_MARK_DISPATCHED, ACTION_MARK_COLLECTED, ACTION_MARK_DELIVERED, ACTION_SAVE_NOTES}
    if ROLE_KITCHEN in roles and action_name in kitchen_actions:
        return True
    if ROLE_CASHIER in roles and action_name in cashier_actions:
        return True
    # Drivers may mark their own dispatched orders delivered; per-order
    # ownership is enforced at the choke-point (can_perform_action with order=).
    if ROLE_DRIVER in roles and action_name == ACTION_MARK_DELIVERED:
        return True
    return False


def _action(name, label, css_class):
    return {"name": name, "label": label, "css_class": css_class}


def action_from_legacy_status(order, raw_status):
    status = (raw_status or "").strip().lower()
    mapping = {
        Order.OrderStatus.CONFIRMED: ACTION_ACCEPT_ORDER,
        Order.OrderStatus.PREPARING: ACTION_START_PREPARING,
        Order.OrderStatus.OUT_FOR_DELIVERY: ACTION_MARK_DISPATCHED,
        Order.OrderStatus.CANCELLED: ACTION_CANCEL_ORDER,
    }
    if status == Order.OrderStatus.READY:
        return ACTION_MARK_READY
    if status == Order.OrderStatus.COMPLETED:
        return ACTION_MARK_DELIVERED if order.is_delivery else ACTION_MARK_COLLECTED
    return mapping.get(status)


def perform_order_action(
    order,
    action,
    actor,
    *,
    staff_notes="",
    handover_notes="",
    cancel_reason="",
    payment_method="",
    payment_amount_received="",
    payment_reference_code="",
    payment_notes="",
    request=None,
):
    if not can_perform_action(actor, action, order=order):
        raise ValueError("You do not have permission to perform this action.")

    unpaid_allowed_actions = {ACTION_MARK_PAID, ACTION_CANCEL_ORDER, ACTION_SAVE_NOTES}
    if order.payment_status != Order.PaymentStatus.PAID and action not in unpaid_allowed_actions:
        raise ValueError("Only paid orders can be prepared on the operations boards.")

    allowed = {item["name"] for item in available_actions(order, user=actor)}
    if action == ACTION_CANCEL_ORDER and order.status not in {
        Order.OrderStatus.COMPLETED,
        Order.OrderStatus.CANCELLED,
    }:
        allowed.add(ACTION_CANCEL_ORDER)
    if action == ACTION_SAVE_NOTES:
        allowed.add(ACTION_SAVE_NOTES)

    if action not in allowed:
        raise ValueError("Action is not allowed for this order.")

    note_fields = []
    cleaned_staff_notes = staff_notes.strip()
    cleaned_handover_notes = handover_notes.strip()
    cleaned_cancel_reason = cancel_reason.strip()

    if cleaned_staff_notes != order.staff_notes:
        order.staff_notes = cleaned_staff_notes
        note_fields.append("staff_notes")
    if cleaned_handover_notes != order.handover_notes:
        order.handover_notes = cleaned_handover_notes
        note_fields.append("handover_notes")
    if action == ACTION_CANCEL_ORDER:
        if not cleaned_cancel_reason:
            raise ValueError("Cancel reason is required.")
        if cleaned_cancel_reason != order.cancel_reason:
            order.cancel_reason = cleaned_cancel_reason
            note_fields.append("cancel_reason")

    if note_fields:
        order.save(update_fields=list(dict.fromkeys(note_fields + ["updated_at"])))

    if action == ACTION_SAVE_NOTES:
        return order

    if action == ACTION_MARK_PAID:
        payment = getattr(order, "payment", None)
        if not payment or payment.provider != Payment.Provider.OFFLINE_PENDING:
            raise ValueError("This order is not awaiting shop payment.")
        if payment.status != Payment.Status.PENDING:
            raise ValueError("This payment is not pending.")
        from apps.payments.services import record_manual_payment

        record_manual_payment(
            payment,
            actor=actor,
            method=payment_method,
            amount_received=payment_amount_received,
            reference_code=payment_reference_code,
            notes=payment_notes,
            request=request,
        )
        order.refresh_from_db()
        return order

    target_status = {
        ACTION_ACCEPT_ORDER: Order.OrderStatus.CONFIRMED,
        ACTION_START_PREPARING: Order.OrderStatus.PREPARING,
        ACTION_MARK_READY: Order.OrderStatus.READY,
        ACTION_MARK_DISPATCHED: Order.OrderStatus.OUT_FOR_DELIVERY,
        ACTION_MARK_COLLECTED: Order.OrderStatus.COMPLETED,
        ACTION_MARK_DELIVERED: Order.OrderStatus.COMPLETED,
        ACTION_CANCEL_ORDER: Order.OrderStatus.CANCELLED,
    }[action]

    old_status = order.status
    order.update_status(target_status, actor)

    if target_status == Order.OrderStatus.READY and old_status != Order.OrderStatus.READY and not order.is_delivery:
        _run_side_effect("order_ready_push", lambda o: _enqueue_push(o, "order_ready", "Your order is ready for pickup."), order)

    if target_status == Order.OrderStatus.OUT_FOR_DELIVERY and old_status != Order.OrderStatus.OUT_FOR_DELIVERY:
        _run_side_effect("order_out_for_delivery_push", lambda o: _enqueue_push(o, "order_out_for_delivery", "Your order is on the way."), order)

    if target_status == Order.OrderStatus.COMPLETED and order.is_delivery and old_status != Order.OrderStatus.COMPLETED:
        _run_side_effect("order_delivered_push", lambda o: _enqueue_push(o, "order_delivered", "Your order has been delivered."), order)

    if target_status in {Order.OrderStatus.COMPLETED, Order.OrderStatus.CANCELLED}:
        _run_side_effect("delivery_run_sync", _sync_delivery_run, order)

    return order


def _sync_delivery_run(order):
    # Lazy import: delivery_services imports helpers from this module.
    from .delivery_services import sync_delivery_run_for_order

    sync_delivery_run_for_order(order)


def _enqueue_push(order, event_type, message):
    if not order.user:
        return
    from apps.core.models import NotificationEvent
    from apps.core.notifications import enqueue_notification

    enqueue_notification(
        channel=NotificationEvent.Channel.PUSH,
        event_type=event_type,
        recipient=str(order.user_id),
        payload={"message": message},
        order=order,
    )


def _run_side_effect(name, func, order):
    try:
        func(order)
    except Exception:
        logger.exception(
            "Operations side effect failed: %s for order %s",
            name,
            order.order_number,
        )
