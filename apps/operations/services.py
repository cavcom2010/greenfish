"""
Staff order-board workflow services.
"""
from django.db.models import Prefetch

from apps.orders.models import Order, OrderItem
from .permissions import can_perform_action

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
ACTION_SAVE_NOTES = "save_notes"


def board_queryset():
    return (
        Order.objects.select_related("user")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.order_by("id")))
        .order_by("created_at")
    )


def kitchen_board_queryset():
    return board_queryset().filter(status__in=KITCHEN_BOARD_STATUSES)


def collection_board_queryset():
    return board_queryset().filter(status__in=COLLECTION_BOARD_STATUSES)


def get_board_counts():
    return {
        "pending_count": Order.objects.filter(status=Order.OrderStatus.PENDING).count(),
        "confirmed_count": Order.objects.filter(status=Order.OrderStatus.CONFIRMED).count(),
        "preparing_count": Order.objects.filter(status=Order.OrderStatus.PREPARING).count(),
        "ready_count": Order.objects.filter(status=Order.OrderStatus.READY).count(),
        "out_for_delivery_count": Order.objects.filter(status=Order.OrderStatus.OUT_FOR_DELIVERY).count(),
        "collection_count": Order.objects.filter(status__in=COLLECTION_BOARD_STATUSES).count(),
        "kanban_confirmed_count": Order.objects.filter(status__in=KANBAN_COLUMNS["confirmed"]).count(),
    }


def get_collection_orders(status_filter="", user=None):
    queryset = collection_board_queryset()
    if status_filter in {Order.OrderStatus.READY, Order.OrderStatus.OUT_FOR_DELIVERY}:
        queryset = queryset.filter(status=status_filter)
    return attach_available_actions(queryset[:50], user=user)


def get_kanban_orders(column_status, user=None):
    statuses = KANBAN_COLUMNS.get(column_status, KANBAN_COLUMNS["confirmed"])
    return attach_available_actions(board_queryset().filter(status__in=statuses), user=user)


def get_all_kanban_columns(user=None):
    return {column: get_kanban_orders(column, user=user) for column in KANBAN_COLUMNS}


def attach_available_actions(orders, user=None):
    for order in orders:
        order.available_actions = available_actions(order, user=user)
    return orders


def available_actions(order, user=None):
    available = []

    if order.status == Order.OrderStatus.PENDING:
        if order.payment_status == Order.PaymentStatus.PAID:
            available.append(_action(ACTION_ACCEPT_ORDER, "Accept Order", "btn-confirm"))

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

    if user is None:
        return available
    return [action for action in available if can_perform_action(user, action["name"])]


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


def perform_order_action(order, action, actor, *, staff_notes="", handover_notes="", cancel_reason=""):
    if not can_perform_action(actor, action):
        raise ValueError("You do not have permission to perform this action.")

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

    if target_status == Order.OrderStatus.OUT_FOR_DELIVERY and old_status != Order.OrderStatus.OUT_FOR_DELIVERY:
        try:
            from apps.sms.services import send_order_out_for_delivery

            send_order_out_for_delivery(order)
        except Exception:
            pass

        try:
            from apps.pwa.services import notify_order_out_for_delivery

            notify_order_out_for_delivery(order)
        except Exception:
            pass

    if target_status == Order.OrderStatus.COMPLETED and order.is_delivery and old_status != Order.OrderStatus.COMPLETED:
        try:
            from apps.sms.services import send_order_delivered

            send_order_delivered(order)
        except Exception:
            pass

        try:
            from apps.pwa.services import notify_order_delivered

            notify_order_delivered(order)
        except Exception:
            pass

    return order
