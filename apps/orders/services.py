"""
Checkout and cart helpers shared by order and payment views.
"""
import hashlib
import json
import logging
import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.media import get_image_variant_url
from apps.menu.models import MenuItem
from apps.offers.models import Offer, VoucherCode

from .models import Order, OrderItem

DEFAULT_PICKUP_MINUTES = 15
VALID_PICKUP_CHOICES = {15, 30, 45, 60}
PHONE_RE = re.compile(r"^(07\d{9}|\+447\d{9})$")
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$", re.IGNORECASE)
SERVICE_TYPE_SESSION_KEY = "service_type"
ACTIVE_OFFER_SESSION_KEY = "active_offer_id"
REWARD_WALLET_SESSION_KEY = "reward_wallet_item_id"
DEFAULT_SERVICE_TYPE = Order.ServiceType.PICKUP
VALID_SERVICE_TYPES = {choice for choice, _ in Order.ServiceType.choices}
GOOGLE_ADDRESS_VALIDATION_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
logger = logging.getLogger(__name__)


def delivery_enabled():
    """Return whether delivery can currently be selected by customers."""
    if not getattr(settings, "DELIVERY_ENABLED", True):
        return False

    from apps.core.models import SiteSettings

    return SiteSettings.get().delivery_enabled


def delivery_minimum_order_amount():
    """Return the minimum food subtotal required for delivery orders."""
    from apps.core.models import SiteSettings

    minimum = SiteSettings.get().delivery_minimum_order_amount_value
    if minimum < Decimal("0.00"):
        return Decimal("15.00")
    return minimum.quantize(Decimal("0.01"))


def _decimal_from_value(value):
    try:
        if value in (None, ""):
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _float_from_value(value):
    parsed = _decimal_from_value(value)
    if parsed is None:
        return None
    return float(parsed)


def haversine_miles(origin_lat, origin_lng, destination_lat, destination_lng):
    """Return the great-circle distance between two coordinates in miles."""
    origin_lat = _float_from_value(origin_lat)
    origin_lng = _float_from_value(origin_lng)
    destination_lat = _float_from_value(destination_lat)
    destination_lng = _float_from_value(destination_lng)
    if None in (origin_lat, origin_lng, destination_lat, destination_lng):
        return None

    radius_miles = 3958.7613
    lat1, lng1, lat2, lng2 = map(
        math.radians,
        [origin_lat, origin_lng, destination_lat, destination_lng],
    )
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return radius_miles * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def delivery_map_settings():
    """Return checkout-safe Google Maps delivery configuration."""
    from apps.core.models import SiteSettings

    site_settings = SiteSettings.get()
    coordinates = site_settings.shop_coordinates
    shop_latitude = coordinates[0] if coordinates else None
    shop_longitude = coordinates[1] if coordinates else None
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    map_enabled = bool(site_settings.is_delivery_enabled and site_settings.delivery_map_enabled)

    return {
        "enabled": map_enabled,
        "configured": bool(map_enabled and api_key and shop_latitude is not None and shop_longitude is not None),
        "api_key": api_key,
        "map_id": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
        "shop_lat": shop_latitude,
        "shop_lng": shop_longitude,
        "radius_miles": site_settings.delivery_radius_value,
    }


def google_address_validation_enabled():
    """Return whether server-side Google Address Validation should run."""
    return bool(
        getattr(settings, "GOOGLE_ADDRESS_VALIDATION_ENABLED", False)
        and getattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "")
    )


def validate_google_delivery_address(delivery_details):
    """Validate and geocode a delivery address with Google's Address Validation API.

    API/network failures intentionally fall back to the existing local coordinate
    radius check, because checkout should not be blocked by a transient provider
    outage after the customer selected a mapped address.
    """
    if not google_address_validation_enabled():
        return False

    address_lines = [
        delivery_details.get("line1", ""),
        delivery_details.get("line2", ""),
        delivery_details.get("city", ""),
        delivery_details.get("postcode", ""),
    ]
    payload = {
        "address": {
            "regionCode": "GB",
            "addressLines": [line for line in address_lines if line],
        },
        "enableUspsCass": False,
    }
    timeout = max(1, int(getattr(settings, "GOOGLE_ADDRESS_VALIDATION_TIMEOUT_SECONDS", 4)))
    try:
        response = requests.post(
            GOOGLE_ADDRESS_VALIDATION_URL,
            params={"key": settings.GOOGLE_MAPS_SERVER_API_KEY},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Google Address Validation failed; falling back to local map validation: %s", exc)
        return False

    result = data.get("result", {})
    verdict = result.get("verdict", {})
    if verdict.get("addressComplete") is False:
        raise ValidationError("Please choose a complete delivery address.")

    geocode = result.get("geocode", {})
    location = geocode.get("location", {})
    latitude = _decimal_from_value(location.get("latitude"))
    longitude = _decimal_from_value(location.get("longitude"))
    if latitude is not None and longitude is not None:
        delivery_details["latitude"] = latitude
        delivery_details["longitude"] = longitude

    formatted_address = result.get("address", {}).get("formattedAddress", "")
    if formatted_address:
        delivery_details["formatted_address"] = formatted_address

    return True


def online_payment_available():
    """Return whether online checkout is available in the current environment."""
    from apps.payments.services import active_payment_provider, payment_provider_configured

    provider = active_payment_provider()
    if settings.DEBUG and not payment_provider_configured(provider):
        return True
    return payment_provider_configured(provider)


def demo_payment_enabled():
    """Allow demo checkout only in debug/local-style environments."""
    from apps.payments.services import active_payment_provider, payment_provider_configured

    return settings.DEBUG and not payment_provider_configured(active_payment_provider())


def payment_fallback_available():
    """Return whether customers may place a held order when online payment is unavailable."""
    return bool(getattr(settings, "PAYMENT_FALLBACK_ENABLED", True))


def payment_fallback_hold_minutes():
    """Return the displayed unpaid fallback hold window in minutes."""
    try:
        return max(1, int(getattr(settings, "PAYMENT_FALLBACK_HOLD_MINUTES", 15)))
    except (TypeError, ValueError):
        return 15


def normalize_phone_number(phone):
    """Normalise user-entered phone numbers for storage and validation."""
    return (phone or "").strip().replace(" ", "")


def normalize_service_type(raw_service_type):
    """Return a supported fulfilment service type."""
    value = (raw_service_type or "").strip().lower()
    if value == Order.ServiceType.DELIVERY and not delivery_enabled():
        return DEFAULT_SERVICE_TYPE
    if value in VALID_SERVICE_TYPES:
        return value
    return DEFAULT_SERVICE_TYPE


def store_service_type(request, raw_service_type):
    """Persist the chosen service type in the session."""
    service_type = normalize_service_type(raw_service_type)
    request.session[SERVICE_TYPE_SESSION_KEY] = service_type
    request.session.modified = True
    return service_type


def store_selected_offer(request, offer):
    """Persist the chosen offer in the session and clear voucher overrides."""
    offer_id = offer.id if hasattr(offer, "id") else int(offer)
    request.session[ACTIVE_OFFER_SESSION_KEY] = offer_id
    request.session.pop(REWARD_WALLET_SESSION_KEY, None)
    request.session.pop("voucher_code", None)
    request.session.modified = True
    return offer_id


def clear_selected_offer(request):
    """Remove any selected offer from the session."""
    if ACTIVE_OFFER_SESSION_KEY in request.session:
        request.session.pop(ACTIVE_OFFER_SESSION_KEY, None)
        request.session.modified = True


def selected_offer_id(request):
    """Return the selected offer id from the session when present."""
    raw_offer_id = request.session.get(ACTIVE_OFFER_SESSION_KEY)
    try:
        return int(raw_offer_id)
    except (TypeError, ValueError):
        return None


def store_reward_wallet_item(request, wallet_item):
    """Persist a wallet reward in the checkout session and clear other discounts."""
    wallet_item_id = wallet_item.id if hasattr(wallet_item, "id") else int(wallet_item)
    request.session[REWARD_WALLET_SESSION_KEY] = wallet_item_id
    request.session.pop(ACTIVE_OFFER_SESSION_KEY, None)
    request.session.pop("voucher_code", None)
    request.session.modified = True
    return wallet_item_id


def clear_reward_wallet_item(request):
    """Remove any wallet reward from the session."""
    if REWARD_WALLET_SESSION_KEY in request.session:
        request.session.pop(REWARD_WALLET_SESSION_KEY, None)
        request.session.modified = True


def selected_reward_wallet_item_id(request):
    """Return the selected wallet reward id from the session when present."""
    raw_wallet_item_id = request.session.get(REWARD_WALLET_SESSION_KEY)
    try:
        return int(raw_wallet_item_id)
    except (TypeError, ValueError):
        return None


def selected_service_type(request):
    """Return the active service type from POST data or the session."""
    return normalize_service_type(
        request.POST.get("service_type")
        or request.GET.get("service_type")
        or request.session.get(SERVICE_TYPE_SESSION_KEY)
    )


def normalize_postcode(postcode):
    """Normalise UK postcodes for display and validation."""
    compact = re.sub(r"\s+", "", (postcode or "").upper())
    if len(compact) > 3:
        return f"{compact[:-3]} {compact[-3:]}"
    return compact


def extract_delivery_details(data):
    """Pull delivery fields from request-like objects into a clean dict."""
    return {
        "line1": (data.get("line1") or data.get("delivery_address_line1", "") or "").strip(),
        "line2": (data.get("line2") or data.get("delivery_address_line2", "") or "").strip(),
        "city": (data.get("city") or data.get("delivery_city", "") or "").strip(),
        "postcode": normalize_postcode(data.get("postcode") or data.get("delivery_postcode", "")),
        "formatted_address": (
            data.get("formatted_address") or data.get("delivery_formatted_address", "") or ""
        ).strip(),
        "place_id": (data.get("place_id") or data.get("delivery_place_id", "") or "").strip(),
        "latitude": _decimal_from_value(data.get("latitude") or data.get("delivery_latitude")),
        "longitude": _decimal_from_value(data.get("longitude") or data.get("delivery_longitude")),
        "distance_miles": _decimal_from_value(data.get("distance_miles") or data.get("delivery_distance_miles")),
    }


def validate_service_details(service_type, delivery_details):
    """Validate fulfilment-specific checkout details."""
    if service_type == Order.ServiceType.DELIVERY and not delivery_enabled():
        raise ValidationError("Delivery is currently unavailable. Please choose pickup.")

    if service_type != Order.ServiceType.DELIVERY:
        return

    if not delivery_details["line1"]:
        raise ValidationError("Delivery address is required.")
    if not delivery_details["city"]:
        raise ValidationError("Delivery city or town is required.")
    if not delivery_details["postcode"]:
        raise ValidationError("Delivery postcode is required.")
    if not POSTCODE_RE.match(delivery_details["postcode"]):
        raise ValidationError("Please enter a valid UK postcode.")

    map_settings = delivery_map_settings()
    if not map_settings["configured"]:
        return

    validate_google_delivery_address(delivery_details)

    latitude = delivery_details.get("latitude")
    longitude = delivery_details.get("longitude")
    if latitude is None or longitude is None:
        raise ValidationError("Please choose your delivery address from the map suggestions.")

    distance = haversine_miles(
        map_settings["shop_lat"],
        map_settings["shop_lng"],
        latitude,
        longitude,
    )
    if distance is None:
        raise ValidationError("We could not confirm that delivery address. Please choose it from the map suggestions.")

    radius = float(map_settings["radius_miles"])
    if distance > radius:
        radius_label = f"{radius:g}"
        raise ValidationError(f"That address is outside our {radius_label} mile delivery area.")

    delivery_details["distance_miles"] = Decimal(str(distance)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def validate_checkout_backend_constraints(service_type, summary, requested_time):
    """Run operational checks that must pass before creating a payment."""
    from .fulfilment import validate_fulfilment_slot
    from .inventory import validate_cart_inventory

    validate_cart_inventory(summary)
    validate_fulfilment_slot(service_type, requested_time)


def validate_delivery_minimum(service_type, subtotal):
    """Validate that delivery orders meet the configured food subtotal minimum."""
    if service_type != Order.ServiceType.DELIVERY:
        return

    minimum = delivery_minimum_order_amount()
    if minimum <= Decimal("0.00"):
        return

    subtotal = (_decimal_from_value(subtotal) or Decimal("0.00")).quantize(Decimal("0.01"))
    if subtotal >= minimum:
        return

    remaining = (minimum - subtotal).quantize(Decimal("0.01"))
    raise ValidationError(
        f"Delivery orders need a food subtotal of at least £{minimum:.2f}. "
        f"Add £{remaining:.2f} more or choose pickup."
    )


def validate_customer_details(customer_name, customer_phone):
    """Validate the minimum checkout details required for an order."""
    if not customer_name:
        raise ValidationError("Name is required.")

    if not customer_phone:
        raise ValidationError("Phone number is required.")

    if not PHONE_RE.match(normalize_phone_number(customer_phone)):
        raise ValidationError(
            "Please enter a valid UK mobile number (for example, 07747055935)."
        )


def parse_pickup_minutes(raw_minutes):
    """Parse the requested pickup time and clamp it to the supported choices."""
    try:
        minutes = int(raw_minutes)
    except (TypeError, ValueError):
        return DEFAULT_PICKUP_MINUTES

    if minutes in VALID_PICKUP_CHOICES:
        return minutes
    return DEFAULT_PICKUP_MINUTES


def requested_pickup_time(raw_minutes):
    """Return the requested pickup time from a submitted pickup choice."""
    return timezone.now() + timezone.timedelta(minutes=parse_pickup_minutes(raw_minutes))


def normalize_modifiers(modifiers):
    """Return a cleaned list of modifiers suitable for session storage."""
    cleaned = []
    if not isinstance(modifiers, list):
        return cleaned

    for modifier in modifiers:
        if not isinstance(modifier, dict):
            continue

        name = str(modifier.get("name", "")).strip()
        if not name:
            continue

        try:
            price = Decimal(str(modifier.get("price", "0"))).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            price = Decimal("0.00")

        cleaned.append(
            {
                "id": modifier.get("id"),
                "name": name,
                "price": str(max(price, Decimal("0.00"))),
            }
        )

    return cleaned


def build_cart_item_id(menu_item_id, modifiers):
    """Create a stable session key for a menu item plus its selected modifiers."""
    modifier_json = json.dumps(normalize_modifiers(modifiers), sort_keys=True)
    digest = hashlib.md5(modifier_json.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"{menu_item_id}_{digest}"


def add_custom_item_to_cart(
    request,
    *,
    item_id,
    name,
    price,
    quantity=1,
    modifiers=None,
    image_url="",
    menu_item_id=None,
):
    """Add an arbitrary purchasable item to the session cart."""
    quantity = max(1, int(quantity))
    modifiers = normalize_modifiers(modifiers or [])
    cart_item_id = build_cart_item_id(item_id, modifiers)
    cart = request.session.get("cart", {})

    if cart_item_id in cart:
        cart[cart_item_id]["quantity"] += quantity
    else:
        cart[cart_item_id] = {
            "menu_item_id": menu_item_id,
            "item_id": item_id,
            "name": name,
            "price": str(price),
            "quantity": quantity,
            "modifiers": modifiers,
            "image_url": image_url,
        }

    request.session["cart"] = cart
    request.session.modified = True
    return cart


def add_menu_item_to_cart(request, menu_item, quantity=1, modifiers=None):
    """Add a menu item to the session cart and return the updated cart payload."""
    return add_custom_item_to_cart(
        request,
        item_id=menu_item.id,
        menu_item_id=menu_item.id,
        name=menu_item.name,
        price=menu_item.price,
        quantity=quantity,
        modifiers=modifiers,
        image_url=get_image_variant_url(menu_item.image, "card") if menu_item.image else "",
    )


def update_session_cart_item(request, item_id, quantity):
    """Update or remove a cart item in the session."""
    cart = request.session.get("cart", {})
    quantity = int(quantity)

    if item_id in cart:
        if quantity > 0:
            cart[item_id]["quantity"] = quantity
        else:
            del cart[item_id]
        request.session["cart"] = cart
        request.session.modified = True

    return cart


def remove_session_cart_item(request, item_id):
    """Remove a session cart item if it exists."""
    cart = request.session.get("cart", {})
    if item_id in cart:
        del cart[item_id]
        request.session["cart"] = cart
        request.session.modified = True
    return cart


def _cart_menu_items(items):
    """Return the menu items referenced by the current basket."""
    menu_item_ids = {
        int(item["menu_item_id"])
        for item in items
        if str(item.get("menu_item_id", "")).isdigit()
    }
    if not menu_item_ids:
        return {}
    return MenuItem.objects.select_related("category").in_bulk(menu_item_ids)


def _offer_discount_base(offer, items, menu_items_by_id):
    """Return the subtotal eligible for a scoped offer."""
    applicable_item_ids = set(offer.applicable_items.values_list("id", flat=True))
    applicable_category_ids = set(offer.applicable_categories.values_list("id", flat=True))
    if not applicable_item_ids and not applicable_category_ids:
        return sum((item["line_total"] for item in items), start=Decimal("0.00")).quantize(Decimal("0.01"))

    qualifying_total = Decimal("0.00")
    for item in items:
        menu_item_id = item.get("menu_item_id")
        if not menu_item_id:
            continue

        menu_item = menu_items_by_id.get(int(menu_item_id))
        if not menu_item:
            continue

        if menu_item.id in applicable_item_ids or menu_item.category_id in applicable_category_ids:
            qualifying_total += item["line_total"]

    return qualifying_total.quantize(Decimal("0.01"))


def _evaluate_offer_application(offer, items, subtotal, menu_items_by_id):
    """Return the discount and validation state for an offer against the basket."""
    if not offer.supports_checkout_discount():
        return {
            "discount": Decimal("0.00"),
            "error": "This offer is not available for online checkout yet.",
            "invalid": True,
        }

    if not offer.is_valid():
        return {
            "discount": Decimal("0.00"),
            "error": "This offer is no longer available.",
            "invalid": True,
        }

    if subtotal < offer.minimum_order_amount:
        return {
            "discount": Decimal("0.00"),
            "error": f"Spend at least GBP {offer.minimum_order_amount:.2f} to use {offer.name}.",
            "invalid": False,
        }

    discount_base = _offer_discount_base(offer, items, menu_items_by_id)
    if discount_base <= Decimal("0.00"):
        return {
            "discount": Decimal("0.00"),
            "error": f"{offer.name} only applies to eligible items in your basket.",
            "invalid": False,
        }

    return {
        "discount": offer.calculate_discount(subtotal, discount_base=discount_base),
        "error": None,
        "invalid": False,
    }


def get_cart_summary(
    cart,
    user=None,
    voucher_code="",
    offer_id=None,
    reward_wallet_item_id=None,
    guest_phone="",
    guest_email="",
):
    """Return a cleaned cart summary for rendering and order creation."""
    items = []
    subtotal = Decimal("0.00")

    for item_id, raw_item in (cart or {}).items():
        try:
            quantity = int(raw_item.get("quantity", 1))
            price = Decimal(str(raw_item.get("price", "0"))).quantize(Decimal("0.01"))
        except (TypeError, ValueError, InvalidOperation):
            continue

        if quantity <= 0 or price < 0:
            continue

        modifiers = normalize_modifiers(raw_item.get("modifiers", []))
        modifiers_total = sum(
            (Decimal(str(modifier.get("price", "0"))) for modifier in modifiers),
            start=Decimal("0.00"),
        )
        line_total = ((price + modifiers_total) * quantity).quantize(Decimal("0.01"))

        legacy_item_id = raw_item.get("item_id")
        menu_item_id = raw_item.get("menu_item_id")
        if not menu_item_id and str(legacy_item_id).isdigit():
            menu_item_id = legacy_item_id

        item = {
            "id": item_id,
            "menu_item_id": menu_item_id,
            "name": str(raw_item.get("name", "")).strip(),
            "quantity": quantity,
            "price": price,
            "modifiers": modifiers,
            "line_total": line_total,
        }
        items.append(item)
        subtotal += line_total

    menu_items_by_id = _cart_menu_items(items)

    voucher = None
    voucher_error = None
    selected_offer = None
    offer_error = None
    offer_invalid = False
    reward_wallet_item = None
    reward_wallet_error = None
    reward_wallet_invalid = False
    applied_offer = None
    discount = Decimal("0.00")
    cleaned_code = (voucher_code or "").strip().upper()

    if cleaned_code:
        try:
            voucher = VoucherCode.objects.select_related("offer").get(
                code=cleaned_code,
                is_active=True,
            )
        except VoucherCode.DoesNotExist:
            voucher_error = "Invalid voucher code."
        else:
            if voucher.is_valid(
                user if getattr(user, "is_authenticated", False) else None,
                guest_phone=guest_phone,
                guest_email=guest_email,
            ):
                evaluation = _evaluate_offer_application(
                    voucher.offer,
                    items,
                    subtotal,
                    menu_items_by_id,
                )
                if evaluation["discount"] > Decimal("0.00"):
                    discount = evaluation["discount"]
                    applied_offer = voucher.offer
                else:
                    voucher_error = evaluation["error"] or "Invalid voucher code."
                    voucher = None
            else:
                voucher_error = "This voucher code has expired or reached its usage limit."
                voucher = None
    elif reward_wallet_item_id:
        try:
            from apps.loyalty.models import RewardWalletItem

            reward_wallet_item = RewardWalletItem.objects.select_related("offer").get(
                pk=reward_wallet_item_id,
                user=user if getattr(user, "is_authenticated", False) else None,
            )
        except (RewardWalletItem.DoesNotExist, TypeError, ValueError):
            reward_wallet_error = "This reward is no longer available."
            reward_wallet_invalid = True
        else:
            if not reward_wallet_item.is_available():
                reward_wallet_error = "This reward is no longer available."
                reward_wallet_invalid = True
            elif not reward_wallet_item.offer:
                reward_wallet_error = "This reward can be claimed from your Rewards Hub."
                reward_wallet_invalid = True
            else:
                evaluation = _evaluate_offer_application(
                    reward_wallet_item.offer,
                    items,
                    subtotal,
                    menu_items_by_id,
                )
                reward_wallet_error = evaluation["error"]
                reward_wallet_invalid = evaluation["invalid"]
                if evaluation["discount"] > Decimal("0.00"):
                    discount = evaluation["discount"]
                    applied_offer = reward_wallet_item.offer
    elif offer_id:
        selected_offer = Offer.objects.filter(pk=offer_id).first()
        if not selected_offer:
            offer_error = "This offer is no longer available."
            offer_invalid = True
        elif not selected_offer.is_available_for_user(user):
            offer_error = "This offer is no longer available."
            offer_invalid = True
        else:
            evaluation = _evaluate_offer_application(
                selected_offer,
                items,
                subtotal,
                menu_items_by_id,
            )
            offer_error = evaluation["error"]
            offer_invalid = evaluation["invalid"]
            if evaluation["discount"] > Decimal("0.00"):
                discount = evaluation["discount"]
                applied_offer = selected_offer

    total = max(Decimal("0.00"), subtotal - discount)
    return {
        "items": items,
        "subtotal": subtotal.quantize(Decimal("0.01")),
        "discount": discount.quantize(Decimal("0.01")),
        "total": total.quantize(Decimal("0.01")),
        "applied_offer": applied_offer,
        "voucher": voucher,
        "voucher_code": cleaned_code if voucher else "",
        "voucher_error": voucher_error,
        "selected_offer": selected_offer,
        "offer_error": offer_error,
        "offer_invalid": offer_invalid,
        "reward_wallet_item": reward_wallet_item,
        "reward_wallet_error": reward_wallet_error,
        "reward_wallet_invalid": reward_wallet_invalid,
    }


def save_customer_profile(user, customer_name, customer_phone, customer_email):
    """Persist customer details back to the logged-in user profile."""
    if not getattr(user, "is_authenticated", False):
        return

    first_name, _, last_name = customer_name.partition(" ")
    user.first_name = first_name
    user.last_name = last_name
    user.phone_number = normalize_phone_number(customer_phone)
    if customer_email:
        user.email = customer_email.strip().lower()
    user.save(update_fields=["first_name", "last_name", "phone_number", "email"])


def create_order_from_summary(
    summary,
    *,
    customer_name,
    customer_phone,
    customer_email="",
    user=None,
    special_instructions="",
    pickup_minutes=DEFAULT_PICKUP_MINUTES,
    service_type=DEFAULT_SERVICE_TYPE,
    delivery_details=None,
    status=Order.OrderStatus.PENDING,
    payment_status=Order.PaymentStatus.PENDING,
):
    """Create an order and its items from a cleaned cart summary."""
    if not summary["items"]:
        raise ValidationError("Your basket is empty.")

    service_type = normalize_service_type(service_type)
    customer_phone = normalize_phone_number(customer_phone)
    customer_email = (customer_email or "").strip().lower()
    delivery_details = extract_delivery_details(delivery_details or {})
    requested_time = requested_pickup_time(pickup_minutes)
    accepted_at = timezone.now() if status == Order.OrderStatus.CONFIRMED else None

    order = Order.objects.create(
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        user=user if getattr(user, "is_authenticated", False) else None,
        service_type=service_type,
        delivery_address_line1=delivery_details["line1"],
        delivery_address_line2=delivery_details["line2"],
        delivery_city=delivery_details["city"],
        delivery_postcode=delivery_details["postcode"],
        delivery_formatted_address=delivery_details["formatted_address"],
        delivery_place_id=delivery_details["place_id"],
        delivery_latitude=delivery_details["latitude"],
        delivery_longitude=delivery_details["longitude"],
        delivery_distance_miles=delivery_details["distance_miles"],
        subtotal=summary["subtotal"],
        discount_amount=summary["discount"],
        total_amount=summary["total"],
        applied_offer=summary["applied_offer"],
        voucher_code=summary["voucher_code"],
        special_instructions=special_instructions,
        requested_pickup_time=requested_time,
        fulfilment_slot_start=requested_time,
        status=status,
        payment_status=payment_status,
        accepted_at=accepted_at,
    )

    for item in summary["items"]:
        menu_item = None
        menu_item_id = item.get("menu_item_id")
        if menu_item_id:
            menu_item = MenuItem.objects.filter(pk=menu_item_id).first()

        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            item_name=item["name"],
            item_price=item["price"],
            preparation_time_minutes=(
                menu_item.preparation_time
                if menu_item
                else OrderItem._meta.get_field("preparation_time_minutes").get_default()
            ),
            quantity=item["quantity"],
            modifiers=item["modifiers"],
        )

    if summary["voucher"]:
        summary["voucher"].record_usage(
            user=user if getattr(user, "is_authenticated", False) else None,
            order=order,
        )
    elif summary["applied_offer"]:
        summary["applied_offer"].increment_usage()

    if summary.get("reward_wallet_item"):
        summary["reward_wallet_item"].mark_used(order)

    from .delivery import apply_delivery_pricing
    from .fulfilment import reserve_fulfilment_slot
    from .inventory import reserve_order_stock

    apply_delivery_pricing(order)
    reserve_fulfilment_slot(order)
    reserve_order_stock(order)

    return order


def clear_checkout_session(request):
    """Remove cart and voucher data from the current session."""
    request.session["cart"] = {}
    request.session.pop("voucher_code", None)
    request.session.pop(ACTIVE_OFFER_SESSION_KEY, None)
    request.session.pop(REWARD_WALLET_SESSION_KEY, None)
    request.session.modified = True
