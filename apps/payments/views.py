"""
Views for the payments app.
"""
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.rate_limits import rate_limit
from apps.orders.access import get_accessible_order_or_404, order_customer_url
from apps.orders.models import Order
from apps.orders.services import (
    clear_checkout_session,
    create_order_from_summary,
    demo_payment_enabled,
    extract_delivery_details,
    get_cart_summary,
    online_payment_available,
    payment_fallback_available,
    payment_fallback_hold_minutes,
    save_customer_profile,
    selected_offer_id,
    selected_reward_wallet_item_id,
    selected_service_type,
    store_service_type,
    requested_fulfilment_time,
    validate_checkout_backend_constraints,
    validate_customer_details,
    validate_delivery_minimum,
    validate_service_details,
)

from .models import Payment, PaymentLog, PaymentWebhookEvent
from .services import (
    StripePaymentService,
    active_payment_provider,
    create_offline_pending_payment,
    normalize_payment_provider,
    payment_provider_configured,
    payment_service_for_provider,
    refresh_payment_status,
    stripe,
    stripe_error,
)

logger = logging.getLogger(__name__)

PAYMENT_FALLBACK_FORM_SESSION_KEY = "payment_fallback_form"
PAYMENT_FALLBACK_PROMPT_SESSION_KEY = "payment_fallback_prompt"


def _checkout_post_snapshot(request):
    fields = [
        "customer_name",
        "customer_phone",
        "customer_email",
        "special_instructions",
        "pickup_time",
        "service_type",
        "delivery_address_line1",
        "delivery_address_line2",
        "delivery_city",
        "delivery_postcode",
    ]
    return {field: (request.POST.get(field, "") or "").strip() for field in fields}


def _store_payment_fallback_prompt(request, *, reason, message):
    request.session[PAYMENT_FALLBACK_FORM_SESSION_KEY] = _checkout_post_snapshot(request)
    request.session[PAYMENT_FALLBACK_PROMPT_SESSION_KEY] = {
        "reason": reason,
        "message": message,
    }
    request.session.modified = True


def _clear_payment_fallback_prompt(request):
    request.session.pop(PAYMENT_FALLBACK_FORM_SESSION_KEY, None)
    request.session.pop(PAYMENT_FALLBACK_PROMPT_SESSION_KEY, None)
    request.session.modified = True


def _fallback_acknowledged(request):
    return request.POST.get("payment_fallback_acknowledged") == "1"


def _fallback_prompt_active(request):
    return bool(request.session.get(PAYMENT_FALLBACK_PROMPT_SESSION_KEY))


def _fallback_reason(request, default="online_payment_unavailable"):
    prompt = request.session.get(PAYMENT_FALLBACK_PROMPT_SESSION_KEY) or {}
    return prompt.get("reason") or default


def _expects_json(request):
    accept = request.headers.get("Accept", "")
    return request.headers.get("HX-Request") or "application/json" in accept


def _payment_error_response(request, message, *, status=400):
    if _expects_json(request):
        return JsonResponse({"error": message}, status=status)
    messages.error(request, message)
    return redirect("orders:checkout")


def _sync_order_payment(order, request=None):
    payment = getattr(order, "payment", None)
    if not payment or payment.is_demo:
        return payment

    external_id = None
    if (
        request is not None
        and payment.provider == Payment.Provider.STRIPE
        and not payment.external_payment_id
    ):
        external_id = request.GET.get("session_id") or None

    return refresh_payment_status(payment, external_id=external_id)


def _create_demo_payment(order, request):
    payment_id = f"demo_{uuid.uuid4().hex[:12]}"
    payment, _ = Payment.objects.get_or_create(
        order=order,
        defaults={
            "provider": Payment.Provider.DEMO,
            "external_payment_id": payment_id,
            "amount": order.total_amount,
            "currency": getattr(settings, "CURRENCY", "GBP"),
            "status": Payment.Status.PENDING,
            "checkout_url": request.build_absolute_uri(
                order_customer_url("payments:demo_checkout", order)
            ),
            "metadata": {"provider": Payment.Provider.DEMO},
        },
    )
    return payment


@require_POST
def create_payment(request):
    """Create a payment for checkout, or a customer-approved fallback hold."""
    service_type = store_service_type(request, request.POST.get("service_type") or selected_service_type(request))

    provider = active_payment_provider()
    provider_ready = payment_provider_configured(provider)
    fallback_ready = payment_fallback_available()
    fallback_acknowledged = _fallback_acknowledged(request)
    fallback_allowed_now = fallback_ready and fallback_acknowledged and (
        not provider_ready or _fallback_prompt_active(request)
    )

    if not online_payment_available() and not fallback_allowed_now:
        message = (
            f"Online card payments are unavailable right now. You can still place your order, "
            f"but you must call or visit the shop to pay within {payment_fallback_hold_minutes()} minutes. "
            "The kitchen will not start until payment is received."
        )
        _store_payment_fallback_prompt(
            request,
            reason="online_payment_unavailable",
            message=message,
        )
        return _payment_error_response(request, message, status=503)

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
        return _payment_error_response(request, "Your basket is empty.")

    customer_name = request.POST.get("customer_name", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()
    customer_email = request.POST.get("customer_email", "").strip()
    special_instructions = request.POST.get("special_instructions", "").strip()
    delivery_details = extract_delivery_details(request.POST)

    try:
        validate_delivery_minimum(service_type, summary["subtotal"])
        validate_customer_details(customer_name, customer_phone)
        validate_service_details(service_type, delivery_details)
        validate_checkout_backend_constraints(
            service_type,
            summary,
            requested_fulfilment_time(request.POST.get("fulfilment_time"), request.POST.get("pickup_time", 15)),
        )
    except ValidationError as exc:
        return _payment_error_response(request, str(exc))

    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
        reward_wallet_item_id=active_reward_wallet_item_id,
        guest_phone=customer_phone,
        guest_email=customer_email,
    )
    if request.session.get("voucher_code") and not summary["voucher"]:
        request.session.pop("voucher_code", None)
        request.session.modified = True
        return _payment_error_response(
            request,
            summary["voucher_error"] or "Invalid voucher code.",
        )
    if active_reward_wallet_item_id and summary["reward_wallet_invalid"]:
        request.session.pop("reward_wallet_item_id", None)
        request.session.modified = True
        return _payment_error_response(
            request,
            summary["reward_wallet_error"] or "This reward is no longer available.",
        )

    save_customer_profile(request.user, customer_name, customer_phone, customer_email)

    order = None
    try:
        with transaction.atomic():
            order = create_order_from_summary(
                summary,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                user=request.user,
                special_instructions=special_instructions,
                pickup_minutes=request.POST.get("pickup_time", 15),
                fulfilment_time=request.POST.get("fulfilment_time"),
                service_type=service_type,
                delivery_details=delivery_details,
                status=Order.OrderStatus.PENDING,
                payment_status=Order.PaymentStatus.PENDING,
            )

            if fallback_allowed_now and not demo_payment_enabled():
                payment = create_offline_pending_payment(
                    order,
                    request,
                    reason=_fallback_reason(request),
                )
            elif demo_payment_enabled():
                payment = _create_demo_payment(order, request)
            else:
                service = payment_service_for_provider(provider)
                if not service:
                    raise RuntimeError("No payment provider is configured.")
                payment = service.create_payment(order, request)
    except Exception:
        logger.exception(
            "Error creating payment for order %s",
            getattr(order, "order_number", "pending"),
        )
        if fallback_ready and not demo_payment_enabled():
            message = (
                f"We could not connect to the card payment provider. You can still place your order, "
                f"but you must call or visit the shop to pay within {payment_fallback_hold_minutes()} minutes. "
                "The kitchen will not start until payment is received."
            )
            _store_payment_fallback_prompt(
                request,
                reason="provider_error",
                message=message,
            )
            return _payment_error_response(request, message, status=503)
        return _payment_error_response(
            request,
            "We could not start the payment. Your basket is still available, so please try again.",
            status=500,
        )

    clear_checkout_session(request)
    _clear_payment_fallback_prompt(request)
    return redirect(payment.checkout_url)


def payment_return(request, order_number):
    """Handle return from checkout."""
    order = get_accessible_order_or_404(request, order_number)
    _sync_order_payment(order, request=request)
    order.refresh_from_db()

    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect(order_customer_url("orders:confirmation", order))

    return render(
        request,
        "payments/payment_status.html",
        {
            "order": order,
            "status": order.payment_status,
            "payment": getattr(order, "payment", None),
            "payment_fallback_hold_minutes": payment_fallback_hold_minutes(),
            "tracking_url": order_customer_url("orders:tracking", order),
            "confirmation_url": order_customer_url("orders:confirmation", order),
        },
    )


def _stripe_webhook(request):
    if stripe is None:
        logger.warning("Stripe webhook received but stripe package is unavailable")
        return HttpResponse("Unavailable", status=503)

    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        logger.warning("Rejected Stripe webhook because STRIPE_WEBHOOK_SECRET is not configured")
        return HttpResponse("Forbidden", status=403)

    signature = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(request.body, signature, webhook_secret)
    except ValueError:
        logger.warning("Rejected Stripe webhook due to invalid payload")
        return HttpResponse("Bad Request", status=400)
    except stripe_error.SignatureVerificationError:
        logger.warning("Rejected Stripe webhook due to invalid signature")
        return HttpResponse("Forbidden", status=403)

    event_type = event.get("type", "")
    session_payload = (event.get("data") or {}).get("object") or {}
    checkout_session_id = session_payload.get("id")
    event_id = event.get("id") or f"stripe:{event_type}:{checkout_session_id or uuid.uuid4().hex}"

    if event_type.startswith("checkout.session.") and checkout_session_id:
        webhook_event, created = PaymentWebhookEvent.objects.get_or_create(
            provider=Payment.Provider.STRIPE,
            event_id=event_id,
            defaults={"event_type": event_type, "payload": event},
        )
        if not created and webhook_event.processed_at:
            return HttpResponse("OK", status=200)
        payment = StripePaymentService().update_payment_status(
            checkout_session_id,
            payload=session_payload,
            event_type=event_type,
        )
        if payment:
            webhook_event.payment = payment
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=["payment", "processed_at"])
            PaymentLog.objects.create(
                payment=payment,
                event_type="webhook_received",
                event_data={"provider": Payment.Provider.STRIPE, "event_type": event_type},
            )

    return HttpResponse("OK", status=200)


@csrf_exempt
@require_POST
@rate_limit("payments-webhook", limit=120, window_seconds=60, response_type="plain")
def webhook(request):
    """Handle payment provider webhooks for the active provider."""
    provider = normalize_payment_provider(active_payment_provider())
    if provider == Payment.Provider.STRIPE:
        return _stripe_webhook(request)
    return HttpResponse("Unavailable", status=503)


def payment_status_api(request, order_number):
    """API endpoint to check payment status."""
    order = get_accessible_order_or_404(request, order_number)
    _sync_order_payment(order)
    order.refresh_from_db()

    return JsonResponse(
        {
            "order_number": order.order_number,
            "status": order.status,
            "payment_status": order.payment_status,
            "paid": order.payment_status == Order.PaymentStatus.PAID,
        }
    )


def demo_checkout(request, order_number):
    """Demo checkout page for testing without a live payment provider."""
    if not demo_payment_enabled():
        raise Http404("Demo checkout is only available in debug mode.")

    order = get_accessible_order_or_404(request, order_number)
    payment = _create_demo_payment(order, request)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "pay":
            payment.status = Payment.Status.PAID
            payment.save(update_fields=["status", "updated_at"])
            order.mark_as_paid()
            return redirect(order_customer_url("orders:confirmation", order))

        if action == "cancel":
            payment.status = Payment.Status.CANCELLED
            payment.save(update_fields=["status", "updated_at"])
            order.status = Order.OrderStatus.CANCELLED
            order.save(update_fields=["status", "updated_at"])
            messages.info(request, "Demo payment cancelled. Your order was not charged.")
            return redirect("orders:checkout")

    return render(
        request,
        "payments/demo_checkout.html",
        {
            "order": order,
            "payment": payment,
        },
    )
