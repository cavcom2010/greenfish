"""
Views for the orders app.
"""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.media import get_image_variant_url
from apps.core.rate_limits import client_identity, consume_rate_limit, session_identity
from apps.mealdeals.models import MealDeal
from apps.menu.models import MenuItem

from .models import Order
from .services import (
    add_custom_item_to_cart,
    add_menu_item_to_cart,
    clear_selected_offer,
    clear_checkout_session,
    create_order_from_summary,
    extract_delivery_details,
    get_cart_summary,
    online_payment_available,
    remove_session_cart_item,
    save_customer_profile,
    selected_offer_id,
    selected_service_type,
    store_service_type,
    validate_service_details,
    update_session_cart_item,
    validate_customer_details,
)

VOUCHER_ATTEMPT_LIMITS = (
    ("session", 8, 300),
    ("ip", 30, 600),
)


def _expects_json(request):
    accept = request.headers.get("Accept", "")
    return request.headers.get("HX-Request") or "application/json" in accept


def _checkout_message_response(request, message, *, status=200, extra=None):
    payload = {
        "success": status < 400,
        "message": message,
    }
    if extra:
        payload.update(extra)

    if request.headers.get("HX-Request"):
        return render(
            request,
            "orders/partials/voucher_message.html",
            {"message": message, "is_error": status >= 400},
            status=status,
        )

    if _expects_json(request):
        return JsonResponse(payload, status=status)

    if status >= 400:
        messages.error(request, message)
    else:
        messages.success(request, message)
    return redirect("orders:checkout")


def _checkout_error_response(request, message, *, status=400):
    if _expects_json(request):
        return JsonResponse({"error": message}, status=status)
    messages.error(request, message)
    return redirect("orders:checkout")


def _voucher_rate_limit_response(request, retry_after):
    message = "Too many voucher attempts. Please wait a few minutes and try again."
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "orders/partials/voucher_message.html",
            {"message": message, "is_error": True},
            status=429,
        )
        response["Retry-After"] = str(retry_after)
        return response

    if _expects_json(request):
        response = JsonResponse(
            {
                "success": False,
                "error": message,
                "retry_after": retry_after,
            },
            status=429,
        )
    else:
        messages.error(request, message)
        response = redirect("orders:checkout")
    response["Retry-After"] = str(retry_after)
    return response


def _enforce_voucher_attempt_limits(request, code):
    if not code:
        return None

    identity_values = {
        "session": session_identity(request),
        "ip": client_identity(request),
    }
    for scope, limit, window_seconds in VOUCHER_ATTEMPT_LIMITS:
        identity = identity_values.get(scope)
        if not identity:
            continue

        try:
            retry_after = consume_rate_limit(
                f"voucher-apply-{scope}",
                identity=identity,
                limit=limit,
                window_seconds=window_seconds,
            )
        except Exception:
            return None

        if retry_after is not None:
            return _voucher_rate_limit_response(request, retry_after)

    return None


def _empty_delivery_context():
    return {
        "delivery_address_line1": "",
        "delivery_address_line2": "",
        "delivery_city": "",
        "delivery_postcode": "",
    }


def _default_delivery_address(user):
    if not getattr(user, "is_authenticated", False):
        return _empty_delivery_context()
    if not hasattr(user, "addresses"):
        return _empty_delivery_context()

    address = (
        user.addresses.filter(address_type="delivery")
        .order_by("-is_default", "-id")
        .first()
    )
    if not address:
        return _empty_delivery_context()

    return {
        "delivery_address_line1": address.street_address,
        "delivery_address_line2": address.apartment,
        "delivery_city": address.city,
        "delivery_postcode": address.postcode,
    }


def _cart_button_response(request):
    summary = get_cart_summary(request.session.get("cart", {}), user=request.user)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "orders/partials/cart_button.html",
            {
                "cart_count": sum(item["quantity"] for item in summary["items"]),
                "cart_total": summary["subtotal"],
            },
        )
    return JsonResponse(
        {
            "success": True,
            "cart_count": sum(item["quantity"] for item in summary["items"]),
        }
    )


def _selected_deal_modifiers(request, deal):
    modifiers = []
    for deal_item in deal.items.prefetch_related("options__menu_item"):
        selected_option_id = request.POST.get(f"item_{deal_item.id}")
        option_queryset = deal_item.options.filter(is_available=True)

        if not selected_option_id and deal_item.min_quantity:
            raise ValidationError(f"Please choose an option for {deal_item.name}.")

        option = option_queryset.filter(menu_item_id=selected_option_id).first()
        if not option and selected_option_id:
            raise ValidationError(f"Selected option for {deal_item.name} is no longer available.")

        if option:
            modifiers.append(
                {
                    "id": option.menu_item_id,
                    "name": f"{deal_item.name}: {option.menu_item.name}",
                    "price": str(option.upgrade_price),
                }
            )

    return modifiers


def cart_view(request):
    """View cart contents."""
    active_offer_id = selected_offer_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
    )
    if active_offer_id and summary["offer_invalid"]:
        clear_selected_offer(request)
        if summary["offer_error"]:
            messages.error(request, summary["offer_error"])
        summary["selected_offer"] = None
    context = {
        "cart_items": summary["items"],
        "subtotal": summary["subtotal"],
        "discount": summary["discount"],
        "cart_total": summary["total"],
        "cart_count": sum(item["quantity"] for item in summary["items"]),
        "service_type": selected_service_type(request),
        "active_offer": summary["selected_offer"],
        "offer_error": summary["offer_error"],
        "voucher_code": summary["voucher_code"],
    }
    template = "desktop/orders/cart.html" if getattr(request, "is_desktop", True) else "orders/cart.html"
    return render(request, template, context)


@require_POST
def add_to_cart(request):
    """Add a menu item or meal deal to the cart."""
    if request.POST.get("service_type"):
        store_service_type(request, request.POST.get("service_type"))
    quantity_raw = request.POST.get("quantity", 1)
    try:
        quantity = max(1, int(quantity_raw))
    except (TypeError, ValueError):
        return _checkout_error_response(request, "Please choose a valid quantity.")

    deal_id = request.POST.get("deal_id")
    if deal_id:
        deal = get_object_or_404(
            MealDeal.objects.prefetch_related("items__options__menu_item"),
            pk=deal_id,
            is_active=True,
        )
        try:
            modifiers = _selected_deal_modifiers(request, deal)
        except ValidationError as exc:
            return _checkout_error_response(request, str(exc))

        add_custom_item_to_cart(
            request,
            item_id=f"deal-{deal.id}",
            name=deal.name,
            price=deal.deal_price,
            quantity=quantity,
            modifiers=modifiers,
            image_url=get_image_variant_url(deal.image, "card") if deal.image else "",
        )
        return _cart_button_response(request)

    menu_item = get_object_or_404(
        MenuItem.objects.select_related("category"),
        pk=request.POST.get("menu_item_id"),
        is_available=True,
    )

    try:
        modifiers = json.loads(request.POST.get("modifiers", "[]") or "[]")
    except json.JSONDecodeError:
        modifiers = []

    add_menu_item_to_cart(request, menu_item, quantity=quantity, modifiers=modifiers)
    return _cart_button_response(request)


@require_POST
def update_cart_item(request, item_id):
    """Update cart item quantity."""
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        return _checkout_error_response(request, "Please choose a valid quantity.")

    update_session_cart_item(request, item_id, quantity)
    return redirect("orders:cart")


@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart."""
    remove_session_cart_item(request, item_id)

    if request.headers.get("HX-Request"):
        summary = get_cart_summary(request.session.get("cart", {}), user=request.user)
        return render(request, "orders/partials/cart_content.html", {"cart_items": summary["items"]})

    return redirect("orders:cart")


def checkout(request):
    """Checkout page."""
    service_type = selected_service_type(request)
    store_service_type(request, service_type)
    active_offer_id = selected_offer_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
    )

    if not summary["items"]:
        clear_checkout_session(request)
        messages.info(request, "Your basket is empty.")
        return redirect("menu:menu")

    if request.session.get("voucher_code") and not summary["voucher"]:
        request.session.pop("voucher_code", None)
        request.session.modified = True

    if active_offer_id and summary["offer_invalid"]:
        clear_selected_offer(request)
        if summary["offer_error"]:
            messages.error(request, summary["offer_error"])
        summary["selected_offer"] = None

    context = {
        "cart_items": summary["items"],
        "subtotal": summary["subtotal"],
        "discount": summary["discount"],
        "total": summary["total"],
        "service_type": service_type,
        "voucher_code": summary["voucher_code"],
        "voucher_error": summary["voucher_error"],
        "active_offer": summary["selected_offer"],
        "offer_error": summary["offer_error"],
        "online_payment_available": online_payment_available(),
        **_default_delivery_address(request.user),
    }
    template = "desktop/orders/checkout.html" if getattr(request, "is_desktop", True) else "orders/checkout.html"
    return render(request, template, context)


@require_POST
def set_service_type(request):
    """Persist the active service type in the session."""
    service_type = store_service_type(request, request.POST.get("service_type"))
    return JsonResponse({"success": True, "service_type": service_type})


@require_POST
def apply_voucher(request):
    """Apply voucher code."""
    code = request.POST.get("code", "").strip().upper()

    if not code:
        request.session.pop("voucher_code", None)
        request.session.modified = True
        return _checkout_message_response(request, "Voucher removed.")

    rate_limit_response = _enforce_voucher_attempt_limits(request, code)
    if rate_limit_response is not None:
        return rate_limit_response

    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=code,
    )
    if summary["voucher"]:
        request.session["voucher_code"] = summary["voucher_code"]
        clear_selected_offer(request)
        request.session.modified = True
        return _checkout_message_response(request, "Voucher applied successfully.")

    request.session.pop("voucher_code", None)
    request.session.modified = True
    return _checkout_message_response(
        request,
        summary["voucher_error"] or "Invalid voucher code.",
        status=400,
    )


def order_confirmation(request, order_number):
    """Order confirmation page."""
    order = get_object_or_404(Order, order_number=order_number)
    template = "desktop/orders/confirmation.html" if getattr(request, "is_desktop", True) else "orders/confirmation.html"
    return render(request, template, {"order": order})


@login_required
def order_board(request):
    """Compatibility route to the operations board."""
    from apps.operations.views import order_board as operations_order_board

    return operations_order_board(request)


@login_required
def order_list_fragment(request):
    """Compatibility route to the operations fragment."""
    from apps.operations.views import order_list_fragment as operations_order_list_fragment

    return operations_order_list_fragment(request)


@login_required
@require_POST
def update_order_status(request, order_id):
    """Compatibility route to the operations action endpoint."""
    from apps.operations.views import order_action

    return order_action(request, order_id)


@login_required
def order_detail_modal(request, order_id):
    """Compatibility route to the operations order detail modal."""
    from apps.operations.views import order_detail_modal as operations_order_detail_modal

    return operations_order_detail_modal(request, order_id)


@require_POST
def pay_instore(request):
    """Create order for pay in store (cash on collection)."""
    service_type = selected_service_type(request)
    store_service_type(request, service_type)
    active_offer_id = selected_offer_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
    )
    if not summary["items"]:
        return _checkout_error_response(request, "Your basket is empty.")

    customer_name = request.POST.get("customer_name", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()
    customer_email = request.POST.get("customer_email", "").strip()
    special_instructions = request.POST.get("special_instructions", "").strip()
    delivery_details = extract_delivery_details(request.POST)

    try:
        validate_customer_details(customer_name, customer_phone)
        validate_service_details(service_type, delivery_details)
        if service_type == Order.ServiceType.DELIVERY:
            raise ValidationError("Delivery orders must be paid online.")
    except ValidationError as exc:
        return _checkout_error_response(request, str(exc))

    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
        guest_phone=customer_phone,
        guest_email=customer_email,
    )
    if request.session.get("voucher_code") and not summary["voucher"]:
        request.session.pop("voucher_code", None)
        request.session.modified = True
        return _checkout_error_response(
            request,
            summary["voucher_error"] or "Invalid voucher code.",
        )

    save_customer_profile(request.user, customer_name, customer_phone, customer_email)

    order = create_order_from_summary(
        summary,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        user=request.user,
        special_instructions=special_instructions,
        pickup_minutes=request.POST.get("pickup_time", 15),
        service_type=service_type,
        delivery_details=delivery_details,
        status=Order.OrderStatus.CONFIRMED,
        payment_status=Order.PaymentStatus.PENDING,
    )

    clear_checkout_session(request)

    try:
        from apps.sms.services import send_order_confirmation

        send_order_confirmation(order)
    except Exception:
        pass

    try:
        from apps.pwa.services import notify_order_confirmed

        notify_order_confirmed(order)
    except Exception:
        pass

    return redirect("orders:confirmation_instore", order_number=order.order_number)


def confirmation_instore(request, order_number):
    """Order confirmation page for pay in store orders."""
    order = get_object_or_404(Order, order_number=order_number)
    template = "desktop/orders/confirmation_instore.html" if getattr(request, "is_desktop", True) else "orders/confirmation_instore.html"
    return render(request, template, {"order": order})


def order_tracking(request, order_number):
    """Public order tracking page - no login required."""
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number)
    template = "desktop/orders/tracking.html" if getattr(request, "is_desktop", True) else "orders/tracking.html"
    return render(request, template, {"order": order})
