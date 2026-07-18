from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import FulfilmentBlackout, FulfilmentCapacityRule, FulfilmentSlotReservation, Order


def _candidate_rule(service_type, slot_start):
    return (
        FulfilmentCapacityRule.objects.filter(
            service_type=service_type,
            day_of_week=slot_start.weekday(),
            start_time__lte=slot_start.time(),
            end_time__gt=slot_start.time(),
            is_active=True,
        )
        .order_by("start_time")
        .first()
    )


def _is_blacked_out(service_type, slot_start):
    return FulfilmentBlackout.objects.filter(
        is_active=True,
        starts_at__lte=slot_start,
        ends_at__gt=slot_start,
        service_type__in=[service_type, FulfilmentBlackout.ServiceType.ALL],
    ).exists()


def _normalise_to_rule_slot(slot_start, rule):
    minute_bucket = (slot_start.minute // rule.slot_minutes) * rule.slot_minutes
    return slot_start.replace(minute=minute_bucket, second=0, microsecond=0)


def validate_fulfilment_slot(service_type, slot_start):
    """Validate service availability and capacity for a requested slot."""
    if not slot_start:
        return None

    slot_start = timezone.localtime(slot_start) if timezone.is_aware(slot_start) else timezone.make_aware(slot_start)
    if _is_blacked_out(service_type, slot_start):
        raise ValidationError("That fulfilment time is unavailable. Please choose another time.")

    rule = _candidate_rule(service_type, slot_start)
    now = timezone.localtime()
    if not rule:
        if slot_start < now:
            raise ValidationError("Please choose a future fulfilment time.")
        return slot_start

    slot_start = _normalise_to_rule_slot(slot_start, rule)

    if slot_start < now + timezone.timedelta(minutes=rule.lead_time_minutes):
        raise ValidationError(f"Please choose a time at least {rule.lead_time_minutes} minutes from now.")

    last_order_at = timezone.datetime.combine(slot_start.date(), rule.end_time)
    last_order_at = timezone.make_aware(last_order_at) - timezone.timedelta(minutes=rule.last_order_minutes_before_close)
    if slot_start > last_order_at:
        raise ValidationError("That time is after the last order cutoff.")

    used = FulfilmentSlotReservation.objects.filter(
        service_type=service_type,
        slot_start=slot_start,
        status__in=[
            FulfilmentSlotReservation.Status.RESERVED,
            FulfilmentSlotReservation.Status.CONFIRMED,
        ],
    ).count()
    if used >= rule.max_orders:
        raise ValidationError("That time is fully booked. Please choose another slot.")
    return slot_start


def _slot_used_count(service_type, slot_start):
    return FulfilmentSlotReservation.objects.filter(
        service_type=service_type,
        slot_start=slot_start,
        status__in=[
            FulfilmentSlotReservation.Status.RESERVED,
            FulfilmentSlotReservation.Status.CONFIRMED,
        ],
    ).count()


def _build_slot_option(service_type, slot_start, *, asap=False, window_minutes=15):
    local_start = timezone.localtime(slot_start)
    local_end = local_start + timezone.timedelta(minutes=window_minutes)
    if service_type == Order.ServiceType.DELIVERY:
        primary = "ASAP" if asap else f"{local_start:%H:%M}-{local_end:%H:%M}"
        secondary = f"Arrives {local_start:%H:%M}-{local_end:%H:%M}"
        summary = f"Arrival window: {local_start:%H:%M}-{local_end:%H:%M}"
    else:
        primary = "ASAP" if asap else f"{local_start:%H:%M}"
        secondary = f"Ready around {local_start:%H:%M}"
        summary = f"Collection estimate: {local_start:%H:%M}"
    return {
        "value": slot_start.isoformat(),
        "primary": primary,
        "secondary": secondary,
        "summary": summary,
        "asap": asap,
    }


def available_fulfilment_options(service_type, *, limit=8):
    """Return same-day fulfilment options for checkout display."""
    service_type = service_type if service_type in {Order.ServiceType.PICKUP, Order.ServiceType.DELIVERY} else Order.ServiceType.PICKUP
    now = timezone.localtime()
    today_rules = FulfilmentCapacityRule.objects.filter(
        service_type=service_type,
        day_of_week=now.weekday(),
        is_active=True,
    )
    has_today_rules = today_rules.exists()
    rule = _candidate_rule(service_type, now)
    if rule:
        step_minutes = rule.slot_minutes
        lead_minutes = rule.lead_time_minutes
        window_minutes = rule.slot_minutes
        end_time = rule.end_time
        last_order_minutes = rule.last_order_minutes_before_close
        max_orders = rule.max_orders
    else:
        step_minutes = 15
        lead_minutes = 15
        window_minutes = 15
        end_time = timezone.datetime.max.time().replace(hour=23, minute=59, second=0, microsecond=0)
        last_order_minutes = 0
        max_orders = None

    earliest = now + timezone.timedelta(minutes=lead_minutes)
    minute_bucket = ((earliest.minute + step_minutes - 1) // step_minutes) * step_minutes
    if minute_bucket >= 60:
        earliest = earliest.replace(minute=0, second=0, microsecond=0) + timezone.timedelta(hours=1)
    else:
        earliest = earliest.replace(minute=minute_bucket, second=0, microsecond=0)

    last_order_at = timezone.datetime.combine(now.date(), end_time)
    last_order_at = timezone.make_aware(last_order_at) - timezone.timedelta(minutes=last_order_minutes)
    options = []
    candidate = earliest
    attempts = 0
    while candidate.date() == now.date() and candidate <= last_order_at and len(options) < limit and attempts < 96:
        attempts += 1
        if not _is_blacked_out(service_type, candidate):
            candidate_rule = _candidate_rule(service_type, candidate)
            if candidate_rule or not has_today_rules:
                used = _slot_used_count(service_type, candidate)
                capacity = candidate_rule.max_orders if candidate_rule else max_orders
                if capacity is None or used < capacity:
                    options.append(
                        _build_slot_option(
                            service_type,
                            candidate,
                            asap=not options,
                            window_minutes=(candidate_rule.slot_minutes if candidate_rule else window_minutes),
                        )
                    )
        candidate += timezone.timedelta(minutes=step_minutes)
    return options


def reserve_fulfilment_slot(order):
    if not order.fulfilment_slot_start:
        return None
    with transaction.atomic():
        requested_start = order.fulfilment_slot_start
        requested_start = (
            timezone.localtime(requested_start)
            if timezone.is_aware(requested_start)
            else timezone.make_aware(requested_start)
        )
        rule = _candidate_rule(order.service_type, requested_start)
        if rule:
            # Serialize capacity checks for this rule so concurrent checkouts
            # cannot both pass the count-then-create validation.
            FulfilmentCapacityRule.objects.select_for_update().get(pk=rule.pk)
        slot_start = validate_fulfilment_slot(order.service_type, order.fulfilment_slot_start)
        if slot_start and order.fulfilment_slot_start != slot_start:
            order.fulfilment_slot_start = slot_start
            order.requested_pickup_time = slot_start
            order.save(update_fields=["fulfilment_slot_start", "requested_pickup_time", "updated_at"])
        return FulfilmentSlotReservation.objects.create(
            order=order,
            service_type=order.service_type,
            slot_start=slot_start or order.fulfilment_slot_start,
        )


def confirm_fulfilment_slot(order):
    reservation = getattr(order, "slot_reservation", None)
    if reservation and reservation.status != FulfilmentSlotReservation.Status.CONFIRMED:
        reservation.status = FulfilmentSlotReservation.Status.CONFIRMED
        reservation.save(update_fields=["status", "updated_at"])


def release_fulfilment_slot(order):
    reservation = getattr(order, "slot_reservation", None)
    if reservation and reservation.status != FulfilmentSlotReservation.Status.RELEASED:
        reservation.status = FulfilmentSlotReservation.Status.RELEASED
        reservation.save(update_fields=["status", "updated_at"])
