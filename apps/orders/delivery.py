import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from .models import DeliveryRun, DeliveryRunOrder, DeliveryZone, Order

logger = logging.getLogger(__name__)


def delivery_quote(distance_miles):
    """Return delivery zone, fee, and ETA minutes for a distance."""
    if distance_miles is None:
        return None, Decimal("0.00"), None
    distance = Decimal(str(distance_miles)).quantize(Decimal("0.01"))
    zone = (
        DeliveryZone.objects.filter(
            is_active=True,
            min_distance_miles__lte=distance,
            max_distance_miles__gte=distance,
        )
        .order_by("max_distance_miles")
        .first()
    )
    if not zone:
        return None, Decimal("0.00"), None
    return zone, zone.fee, zone.estimated_minutes


def google_route_eta_minutes(destination_latitude, destination_longitude):
    """Return Google route duration in minutes when Routes API is configured."""
    api_key = (
        getattr(settings, "GOOGLE_ROUTES_API_KEY", "")
        or getattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "")
    )
    if not getattr(settings, "GOOGLE_ROUTES_API_ENABLED", False) or not api_key:
        return None
    origin = getattr(settings, "SHOP_LATITUDE", ""), getattr(settings, "SHOP_LONGITUDE", "")
    if not all(origin) or not destination_latitude or not destination_longitude:
        return None

    payload = {
        "origins": [{"waypoint": {"location": {"latLng": {"latitude": float(origin[0]), "longitude": float(origin[1])}}}}],
        "destinations": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {
                            "latitude": float(destination_latitude),
                            "longitude": float(destination_longitude),
                        }
                    }
                }
            }
        ],
        "travelMode": "DRIVE",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "duration",
    }
    try:
        response = requests.post(
            "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            json=payload,
            headers=headers,
            timeout=max(1, int(getattr(settings, "GOOGLE_ROUTES_TIMEOUT_SECONDS", 4))),
        )
        response.raise_for_status()
        rows = response.json()
    except Exception as exc:
        logger.warning("Google route ETA failed: %s", exc)
        return None

    if not rows:
        return None
    duration = rows[0].get("duration", "")
    if not duration.endswith("s"):
        return None
    try:
        return max(1, round(int(duration[:-1]) / 60))
    except (TypeError, ValueError):
        return None


def apply_delivery_pricing(order):
    if not order.is_delivery:
        return order
    zone, fee, eta = delivery_quote(order.delivery_distance_miles)
    route_eta = google_route_eta_minutes(order.delivery_latitude, order.delivery_longitude)
    order.delivery_fee = fee
    order.delivery_zone_name = zone.name if zone else ""
    order.delivery_eta_minutes = route_eta or eta
    order.total_amount = max(Decimal("0.00"), order.subtotal - order.discount_amount + order.delivery_fee)
    order.save(update_fields=["delivery_fee", "delivery_zone_name", "delivery_eta_minutes", "total_amount", "updated_at"])
    return order


def create_delivery_run(*, driver, orders, planned_departure_at=None, notes=""):
    run = DeliveryRun.objects.create(
        driver=driver,
        planned_departure_at=planned_departure_at,
        notes=notes,
    )
    for sequence, order in enumerate(orders, start=1):
        DeliveryRunOrder.objects.create(run=run, order=order, sequence=sequence)
        order.delivery_driver = driver
        order.save(update_fields=["delivery_driver", "updated_at"])
    return run


def dispatch_delivery_run(run, actor=None):
    run.status = DeliveryRun.Status.DISPATCHED
    run.dispatched_at = timezone.now()
    run.save(update_fields=["status", "dispatched_at", "updated_at"])
    for run_order in run.run_orders.select_related("order"):
        run_order.order.update_status(Order.OrderStatus.OUT_FOR_DELIVERY, changed_by=actor)
    return run
