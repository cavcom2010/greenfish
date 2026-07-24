"""
Delivery-run orchestration: assigning orders to drivers, dispatching runs,
and the driver's own delivered flow. Thin layer over apps.orders.delivery —
all customer notifications ride the existing outbox (email/SMS via
Order.update_status, push enqueued here for the run-dispatch path, which
bypasses perform_order_action).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.delivery import delivery_quote, dispatch_delivery_run, google_route_eta_minutes
from apps.orders.models import DeliveryDriver, DeliveryRun, DeliveryRunOrder, Order

logger = logging.getLogger(__name__)

DEFAULT_ETA_MINUTES = 30

# Order states a stop can be assigned from (kitchen may still be cooking).
ASSIGNABLE_STATUSES = {
    Order.OrderStatus.CONFIRMED,
    Order.OrderStatus.PREPARING,
    Order.OrderStatus.READY,
}


def _per_stop_minutes():
    return int(getattr(settings, "DELIVERY_PER_STOP_MINUTES", 7))


def get_driver_profile(user):
    """The active DeliveryDriver linked to this login, if any."""
    if not getattr(user, "is_authenticated", False):
        return None
    return DeliveryDriver.objects.filter(user=user, is_active=True).first()


def get_active_drivers():
    return DeliveryDriver.objects.filter(is_active=True)


def get_or_create_draft_run(driver):
    """The driver's single DRAFT run (locked), created on demand."""
    run = (
        DeliveryRun.objects.select_for_update()
        .filter(driver=driver, status=DeliveryRun.Status.DRAFT)
        .first()
    )
    if run is None:
        run = DeliveryRun.objects.create(driver=driver)
    return run


def assign_order_to_run(order, driver, actor=None):
    """Put a paid delivery order onto the driver's draft run (moving it off
    another draft run if needed)."""
    if not order.is_delivery:
        raise ValueError("Only delivery orders can be assigned to a driver.")
    if order.payment_status != Order.PaymentStatus.PAID:
        raise ValueError("Only paid orders can be assigned to a driver.")
    if order.status not in ASSIGNABLE_STATUSES:
        raise ValueError("Order cannot be assigned in its current status.")

    existing = getattr(order, "delivery_run_order", None)
    if existing is not None:
        source_run = existing.run
        if source_run.status != DeliveryRun.Status.DRAFT:
            raise ValueError("Order is already on an active run.")
        if source_run.driver_id == driver.id:
            return existing
        _remove_run_order(existing)

    run = get_or_create_draft_run(driver)
    max_sequence = (
        run.run_orders.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    )
    run_order = DeliveryRunOrder.objects.create(run=run, order=order, sequence=max_sequence + 1)
    order.delivery_driver = driver
    order.save(update_fields=["delivery_driver", "updated_at"])
    return run_order


def unassign_order(order, actor=None):
    """Take an order off its DRAFT run; active runs are immutable."""
    run_order = getattr(order, "delivery_run_order", None)
    if run_order is None:
        return
    if run_order.run.status != DeliveryRun.Status.DRAFT:
        raise ValueError("Orders on an active run cannot be unassigned.")
    _remove_run_order(run_order)
    order.delivery_driver = None
    order.save(update_fields=["delivery_driver", "updated_at"])


def _remove_run_order(run_order):
    """Delete a stop, resequence the rest, and drop the run if emptied."""
    run = run_order.run
    run_order.delete()
    remaining = list(run.run_orders.order_by("sequence"))
    if not remaining:
        run.delete()
        return
    for index, stop in enumerate(remaining, start=1):
        if stop.sequence != index:
            stop.sequence = index
            stop.save(update_fields=["sequence"])


def compute_run_etas(run, now=None):
    """Stamp eta_at per stop: base travel estimate + a per-stop increment."""
    now = now or timezone.now()
    per_stop = _per_stop_minutes()
    for run_order in run.run_orders.select_related("order").order_by("sequence"):
        order = run_order.order
        base = google_route_eta_minutes(order.delivery_latitude, order.delivery_longitude)
        if base is None:
            base = order.delivery_eta_minutes
        if base is None:
            _zone, _fee, zone_minutes = delivery_quote(order.delivery_distance_miles)
            base = zone_minutes
        if base is None:
            base = DEFAULT_ETA_MINUTES
        run_order.eta_at = now + timedelta(minutes=base + (run_order.sequence - 1) * per_stop)
        run_order.save(update_fields=["eta_at"])


def dispatch_run(run, actor=None):
    """Dispatch a DRAFT run: prune cancelled stops, compute ETAs, flip orders
    to OUT_FOR_DELIVERY (email/SMS fire via update_status), and enqueue the
    push that the run path would otherwise miss."""
    if run.status != DeliveryRun.Status.DRAFT:
        raise ValueError("Only draft runs can be dispatched.")

    for run_order in list(run.run_orders.select_related("order")):
        if run_order.order.status == Order.OrderStatus.CANCELLED:
            _remove_run_order(run_order)

    if not DeliveryRun.objects.filter(pk=run.pk).exists():
        # Every stop was cancelled; _remove_run_order deleted the run.
        raise ValueError("Run has no orders left to dispatch.")

    compute_run_etas(run)
    dispatch_delivery_run(run, actor)

    from .services import _enqueue_push, _run_side_effect

    for run_order in run.run_orders.select_related("order"):
        _run_side_effect(
            "order_out_for_delivery_push",
            lambda o: _enqueue_push(o, "order_out_for_delivery", "Your order is on the way."),
            run_order.order,
        )
    return run


def driver_mark_delivered(order, actor, *, request=None):
    """Driver (or staff) completes a stop. Permission/ownership enforced by
    perform_order_action -> can_perform_action(order=); the delivery_run_sync
    side-effect stamps run_order.delivered_at and closes the run."""
    from .services import ACTION_MARK_DELIVERED, perform_order_action

    return perform_order_action(order, ACTION_MARK_DELIVERED, actor, request=request)


def maybe_complete_run(run):
    """Close a dispatched run once every stop's order is terminal."""
    if run.status != DeliveryRun.Status.DISPATCHED:
        return
    statuses = list(run.run_orders.values_list("order__status", flat=True))
    if not statuses:
        return
    terminal = {Order.OrderStatus.COMPLETED, Order.OrderStatus.CANCELLED}
    if not all(status in terminal for status in statuses):
        return
    all_cancelled = all(status == Order.OrderStatus.CANCELLED for status in statuses)
    run.status = DeliveryRun.Status.CANCELLED if all_cancelled else DeliveryRun.Status.COMPLETED
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at", "updated_at"])


def sync_delivery_run_for_order(order):
    """Keep run state consistent after a terminal order transition made
    outside the driver flow (ops-board cancel/complete)."""
    run_order = getattr(order, "delivery_run_order", None)
    if run_order is None:
        return
    run = run_order.run
    if run.status == DeliveryRun.Status.DRAFT and order.status == Order.OrderStatus.CANCELLED:
        with transaction.atomic():
            _remove_run_order(run_order)
            order.delivery_driver = None
            order.save(update_fields=["delivery_driver", "updated_at"])
    elif run.status == DeliveryRun.Status.DISPATCHED:
        if order.status == Order.OrderStatus.COMPLETED and run_order.delivered_at is None:
            run_order.delivered_at = timezone.now()
            run_order.save(update_fields=["delivered_at"])
        maybe_complete_run(run)


def get_dispatch_panel_context():
    """Data for the staff dispatch panel."""
    from .services import board_queryset

    unassigned_orders = (
        board_queryset()
        .filter(
            service_type=Order.ServiceType.DELIVERY,
            status__in=ASSIGNABLE_STATUSES,
            delivery_run_order__isnull=True,
        )
        .order_by("created_at")
    )
    run_queryset = (
        DeliveryRun.objects.select_related("driver")
        .prefetch_related("run_orders__order")
    )
    return {
        "unassigned_orders": unassigned_orders,
        "draft_runs": run_queryset.filter(status=DeliveryRun.Status.DRAFT).order_by("created_at"),
        "dispatched_runs": run_queryset.filter(status=DeliveryRun.Status.DISPATCHED).order_by("dispatched_at"),
        "drivers": get_active_drivers(),
    }


def get_driver_runs(driver):
    """The driver's current draft and dispatched runs for the driver board."""
    run_queryset = DeliveryRun.objects.prefetch_related("run_orders__order")
    return {
        "draft_run": run_queryset.filter(driver=driver, status=DeliveryRun.Status.DRAFT).first(),
        "dispatched_run": run_queryset.filter(driver=driver, status=DeliveryRun.Status.DISPATCHED).first(),
    }
