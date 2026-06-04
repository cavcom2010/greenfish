from django.core.exceptions import ValidationError
from django.db.models import Count
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
    if not rule:
        return slot_start

    slot_start = _normalise_to_rule_slot(slot_start, rule)

    now = timezone.localtime()
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


def reserve_fulfilment_slot(order):
    if not order.fulfilment_slot_start:
        return None
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
