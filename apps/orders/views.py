"""
Views for the orders app.
"""
import json
from decimal import Decimal

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

from .access import get_accessible_order_or_404, order_customer_url, request_can_access_order, request_has_order_token
from .fulfilment import available_fulfilment_options
from .models import Order, OrderIssue
from .services import (
    add_custom_item_to_cart,
    add_menu_item_to_cart,
    clear_selected_offer,
    clear_reward_wallet_item,
    clear_checkout_session,
    delivery_enabled,
    delivery_map_settings,
    delivery_minimum_order_amount,
    extract_delivery_details,
    get_cart_summary,
    max_cart_item_quantity,
    normalize_cart_quantity,
    online_payment_available,
    payment_fallback_available,
    payment_fallback_hold_minutes,
    remove_session_cart_item,
    selected_offer_id,
    selected_reward_wallet_item_id,
    selected_service_type,
    store_service_type,
    update_session_cart_item,
    validate_delivery_minimum,
    validate_service_details,
)

PAYMENT_FALLBACK_FORM_SESSION_KEY = "payment_fallback_form"
PAYMENT_FALLBACK_PROMPT_SESSION_KEY = "payment_fallback_prompt"


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
        "delivery_formatted_address": "",
        "delivery_place_id": "",
        "delivery_latitude": "",
        "delivery_longitude": "",
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
    cart_count = sum(item["quantity"] for item in summary["items"])
    if request.headers.get("HX-Request"):
        return render(
            request,
            "orders/partials/cart_button.html",
            {
                "cart_count": cart_count,
                "cart_total": summary["subtotal"],
            },
        )
    return JsonResponse(
        {
            "success": True,
            "cart_count": cart_count,
            "cart_total": f"{summary['total']:.2f}",
            "max_cart_item_quantity": max_cart_item_quantity(),
        }
    )


def _cart_state_payload(request):
    summary = get_cart_summary(request.session.get("cart", {}), user=request.user)
    return {
        "success": True,
        "cart_count": sum(item["quantity"] for item in summary["items"]),
        "cart_total": f"{summary['total']:.2f}",
        "max_cart_item_quantity": max_cart_item_quantity(),
    }


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
    active_reward_wallet_item_id = selected_reward_wallet_item_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
        reward_wallet_item_id=active_reward_wallet_item_id,
    )
    if active_offer_id and summary["offer_invalid"]:
        clear_selected_offer(request)
        if summary["offer_error"]:
            messages.error(request, summary["offer_error"])
        summary["selected_offer"] = None
    if active_reward_wallet_item_id and summary["reward_wallet_invalid"]:
        clear_reward_wallet_item(request)
        if summary["reward_wallet_error"]:
            messages.error(request, summary["reward_wallet_error"])
        summary["reward_wallet_item"] = None
    context = {
        "cart_items": summary["items"],
        "subtotal": summary["subtotal"],
        "discount": summary["discount"],
        "cart_total": summary["total"],
        "cart_count": sum(item["quantity"] for item in summary["items"]),
        "service_type": selected_service_type(request),
        "delivery_enabled": delivery_enabled(),
        "active_offer": summary["selected_offer"],
        "offer_error": summary["offer_error"],
        "reward_wallet_item": summary["reward_wallet_item"],
        "reward_wallet_error": summary["reward_wallet_error"],
        "voucher_code": summary["voucher_code"],
    }
    template = "desktop/orders/cart.html" if getattr(request, "is_desktop", True) else "orders/cart.html"
    return render(request, template, context)


def cart_drawer(request):
    """Return cart drawer content via HTMX."""
    active_offer_id = selected_offer_id(request)
    active_reward_wallet_item_id = selected_reward_wallet_item_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
        reward_wallet_item_id=active_reward_wallet_item_id,
    )
    context = {
        "cart_items": summary["items"],
        "subtotal": summary["subtotal"],
        "discount": summary["discount"],
        "cart_total": summary["total"],
        "cart_count": sum(item["quantity"] for item in summary["items"]),
        "active_offer": summary["selected_offer"],
        "offer_error": summary["offer_error"],
        "reward_wallet_item": summary["reward_wallet_item"],
        "reward_wallet_error": summary["reward_wallet_error"],
        "voucher_code": summary["voucher_code"],
    }
    return render(request, "orders/partials/cart_drawer.html", context)


@require_POST
def add_to_cart(request):
    """Add a menu item or meal deal to the cart."""
    if request.POST.get("service_type"):
        store_service_type(request, request.POST.get("service_type"))
    quantity_raw = request.POST.get("quantity", 1)
    try:
        quantity = normalize_cart_quantity(quantity_raw)
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
        quantity = normalize_cart_quantity(request.POST.get("quantity", 1), allow_zero=True)
    except (TypeError, ValueError):
        return _checkout_error_response(request, "Please choose a valid quantity.")

    update_session_cart_item(request, item_id, quantity)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(_cart_state_payload(request))
    return redirect("orders:cart")


@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart."""
    remove_session_cart_item(request, item_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(_cart_state_payload(request))

    if request.headers.get("HX-Request"):
        active_offer_id = selected_offer_id(request)
        active_reward_wallet_item_id = selected_reward_wallet_item_id(request)
        summary = get_cart_summary(
            request.session.get("cart", {}),
            user=request.user,
            voucher_code=request.session.get("voucher_code", ""),
            offer_id=active_offer_id,
            reward_wallet_item_id=active_reward_wallet_item_id,
        )
        cart_count = sum(item["quantity"] for item in summary["items"])
        response = render(
            request,
            "orders/partials/cart_drawer.html",
            {
                "cart_items": summary["items"],
                "subtotal": summary["subtotal"],
                "discount": summary["discount"],
                "cart_total": summary["total"],
                "cart_count": cart_count,
                "active_offer": summary["selected_offer"],
                "offer_error": summary["offer_error"],
                "reward_wallet_item": summary["reward_wallet_item"],
                "reward_wallet_error": summary["reward_wallet_error"],
                "voucher_code": summary["voucher_code"],
            },
        )
        response["HX-Trigger"] = json.dumps(
            {"cart-updated": {"cart_count": cart_count, "cart_total": f"{summary['total']:.2f}"}}
        )
        return response

    return redirect("orders:cart")


def checkout(request):
    """Checkout page."""
    service_type = selected_service_type(request)
    store_service_type(request, service_type)
    active_offer_id = selected_offer_id(request)
    active_reward_wallet_item_id = selected_reward_wallet_item_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
        reward_wallet_item_id=active_reward_wallet_item_id,
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

    if active_reward_wallet_item_id and summary["reward_wallet_invalid"]:
        clear_reward_wallet_item(request)
        if summary["reward_wallet_error"]:
            messages.error(request, summary["reward_wallet_error"])
        summary["reward_wallet_item"] = None

    checkout_form = request.session.get(PAYMENT_FALLBACK_FORM_SESSION_KEY, {})
    default_customer_name = checkout_form.get("customer_name", "")
    default_customer_phone = checkout_form.get("customer_phone", "")
    default_customer_email = checkout_form.get("customer_email", "")
    if getattr(request.user, "is_authenticated", False):
        default_customer_name = default_customer_name or getattr(request.user, "full_name", "") or request.user.get_full_name()
        default_customer_phone = default_customer_phone or getattr(request.user, "phone_number", "")
        default_customer_email = default_customer_email or getattr(request.user, "email", "")

    delivery_minimum = delivery_minimum_order_amount()
    delivery_minimum_remaining = max(Decimal("0.00"), delivery_minimum - summary["subtotal"]).quantize(Decimal("0.01"))

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
        "reward_wallet_item": summary["reward_wallet_item"],
        "reward_wallet_error": summary["reward_wallet_error"],
        "online_payment_available": online_payment_available(),
        "payment_fallback_available": payment_fallback_available(),
        "payment_fallback_hold_minutes": payment_fallback_hold_minutes(),
        "payment_fallback_prompt": request.session.get(PAYMENT_FALLBACK_PROMPT_SESSION_KEY),
        "checkout_form": checkout_form,
        "default_customer_name": default_customer_name,
        "default_customer_phone": default_customer_phone,
        "default_customer_email": default_customer_email,
        "delivery_enabled": delivery_enabled(),
        "delivery_map": delivery_map_settings(),
        "delivery_minimum_order_amount": delivery_minimum,
        "delivery_minimum_met": delivery_minimum_remaining == Decimal("0.00"),
        "delivery_minimum_remaining": delivery_minimum_remaining,
        "pickup_time_options": available_fulfilment_options(Order.ServiceType.PICKUP),
        "delivery_time_options": available_fulfilment_options(Order.ServiceType.DELIVERY) if delivery_enabled() else [],
        **_default_delivery_address(request.user),
    }
    template = "desktop/orders/checkout.html" if getattr(request, "is_desktop", True) else "orders/checkout.html"
    return render(request, template, context)


@require_POST
def delivery_quote(request):
    """Return the current delivery fee and payable total for checkout."""
    service_type = store_service_type(request, request.POST.get("service_type") or selected_service_type(request))
    if service_type != Order.ServiceType.DELIVERY:
        return JsonResponse({"success": False, "error": "Delivery is not selected."}, status=400)

    active_offer_id = selected_offer_id(request)
    active_reward_wallet_item_id = selected_reward_wallet_item_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
        reward_wallet_item_id=active_reward_wallet_item_id,
    )
    if not summary["items"]:
        return JsonResponse({"success": False, "error": "Your basket is empty."}, status=400)

    try:
        validate_delivery_minimum(service_type, summary["subtotal"])
    except ValidationError as exc:
        return JsonResponse(
            {
                "success": True,
                "quote_ready": False,
                "error": str(exc),
                "subtotal": f"{summary['subtotal']:.2f}",
                "discount": f"{summary['discount']:.2f}",
                "delivery_fee": "0.00",
                "total": f"{summary['total']:.2f}",
            }
        )

    delivery_details = extract_delivery_details(request.POST)
    map_settings = delivery_map_settings()
    if map_settings["configured"] and not (
        delivery_details["latitude"] is not None and delivery_details["longitude"] is not None
    ):
        return JsonResponse(
            {
                "success": True,
                "quote_ready": False,
                "message": "Choose your delivery address to calculate the delivery fee.",
                "subtotal": f"{summary['subtotal']:.2f}",
                "discount": f"{summary['discount']:.2f}",
                "delivery_fee": "0.00",
                "total": f"{summary['total']:.2f}",
            }
        )

    try:
        validate_service_details(service_type, delivery_details)
    except ValidationError as exc:
        return JsonResponse(
            {
                "success": True,
                "quote_ready": False,
                "error": str(exc),
                "subtotal": f"{summary['subtotal']:.2f}",
                "discount": f"{summary['discount']:.2f}",
                "delivery_fee": "0.00",
                "total": f"{summary['total']:.2f}",
            }
        )

    from .delivery import delivery_quote as calculate_delivery_quote

    zone, fee, eta = calculate_delivery_quote(delivery_details.get("distance_miles"))
    total = max(Decimal("0.00"), summary["subtotal"] - summary["discount"] + fee).quantize(Decimal("0.01"))

    return JsonResponse(
        {
            "success": True,
            "quote_ready": True,
            "delivery_fee": f"{fee:.2f}",
            "delivery_zone_name": zone.name if zone else "",
            "delivery_eta_minutes": eta,
            "delivery_distance_miles": (
                f"{delivery_details['distance_miles']:.2f}"
                if delivery_details.get("distance_miles") is not None
                else ""
            ),
            "subtotal": f"{summary['subtotal']:.2f}",
            "discount": f"{summary['discount']:.2f}",
            "total": f"{total:.2f}",
        }
    )


@require_POST
def set_service_type(request):
    """Persist the active service type in the session."""
    requested_service_type = request.POST.get("service_type")
    service_type = store_service_type(request, request.POST.get("service_type"))
    return JsonResponse(
        {
            "success": True,
            "service_type": service_type,
            "delivery_enabled": delivery_enabled(),
            "delivery_coerced": requested_service_type == Order.ServiceType.DELIVERY
            and service_type != Order.ServiceType.DELIVERY,
        }
    )


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
        clear_reward_wallet_item(request)
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
    order = get_accessible_order_or_404(request, order_number)
    template = "desktop/orders/confirmation.html" if getattr(request, "is_desktop", True) else "orders/confirmation.html"
    return render(request, template, {"order": order, "tracking_url": order_customer_url("orders:tracking", order)})


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
    """Legacy endpoint retained for compatibility; customer orders are online-only."""
    return _checkout_error_response(request, "Orders must be paid online.")


def confirmation_instore(request, order_number):
    """Order confirmation page for pay in store orders."""
    order = get_accessible_order_or_404(request, order_number)
    template = "desktop/orders/confirmation_instore.html" if getattr(request, "is_desktop", True) else "orders/confirmation_instore.html"
    return render(request, template, {"order": order, "tracking_url": order_customer_url("orders:tracking", order)})


def order_tracking(request, order_number):
    """Public order tracking page - no login required."""
    order = get_accessible_order_or_404(
        request,
        order_number,
        queryset=Order.objects.prefetch_related("items", "issues"),
    )
    can_claim_order = (
        getattr(request.user, "is_authenticated", False)
        and not order.user_id
        and request_has_order_token(request, order)
        and (not order.customer_email or order.customer_email.lower() == request.user.email.lower())
    )
    template = "desktop/orders/tracking.html" if getattr(request, "is_desktop", True) else "orders/tracking.html"
    return render(
        request,
        template,
        {
            "order": order,
            "tracking_url": order_customer_url("orders:tracking", order),
            "issue_url": order_customer_url("orders:create_issue", order),
            "claim_url": order_customer_url("accounts:claim_guest_order", order),
            "can_claim_order": can_claim_order,
            "can_prompt_guest_claim": not order.user_id and request_has_order_token(request, order),
        },
    )


def create_order_issue(request, order_number):
    """Let a customer raise a structured issue for their own order."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "issues"),
        order_number=order_number,
    )
    if not request_can_access_order(request, order):
        from django.http import Http404

        raise Http404("Order not found")
    if request.method == "POST":
        issue_type = request.POST.get("issue_type", "")
        description = request.POST.get("description", "").strip()
        refund_amount_raw = request.POST.get("requested_refund_amount", "").strip()
        refund_amount = None
        if refund_amount_raw:
            try:
                refund_amount = Decimal(refund_amount_raw)
            except Exception:
                messages.error(request, "Please enter a valid refund amount.")
                return redirect(order_customer_url("orders:create_issue", order))

        valid_issue_types = {choice for choice, _ in OrderIssue.IssueType.choices}
        if issue_type not in valid_issue_types:
            messages.error(request, "Please choose the issue type.")
            return redirect(order_customer_url("orders:create_issue", order))
        if len(description) < 10:
            messages.error(request, "Please describe what happened.")
            return redirect(order_customer_url("orders:create_issue", order))

        issue = OrderIssue.objects.create(
            order=order,
            user=request.user if getattr(request.user, "is_authenticated", False) else None,
            issue_type=issue_type,
            description=description,
            requested_refund_amount=refund_amount,
        )
        from apps.core.customer_notifications import enqueue_order_issue_received

        enqueue_order_issue_received(issue)
        messages.success(request, "Your issue has been sent to the team.")
        return redirect(order_customer_url("orders:tracking", order))

    context = {
        "order": order,
        "issue_types": OrderIssue.IssueType.choices,
        "tracking_url": order_customer_url("orders:tracking", order),
    }
    template = "desktop/orders/create_issue.html" if getattr(request, "is_desktop", True) else "orders/create_issue.html"
    return render(request, template, context)
