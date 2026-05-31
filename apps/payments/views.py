"""
Views for the payments app.
"""
import logging
import uuid
from secrets import compare_digest

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.rate_limits import rate_limit
from apps.orders.models import Order
from apps.orders.services import (
    clear_checkout_session,
    create_order_from_summary,
    demo_payment_enabled,
    extract_delivery_details,
    get_cart_summary,
    online_payment_available,
    save_customer_profile,
    selected_offer_id,
    selected_service_type,
    store_service_type,
    validate_customer_details,
    validate_service_details,
)

from .models import Payment, PaymentLog
from .services import (
    StripePaymentService,
    active_payment_provider,
    normalize_payment_provider,
    payment_service_for_provider,
    refresh_payment_status,
    stripe,
    stripe_error,
)

logger = logging.getLogger(__name__)


def _expects_json(request):
    accept = request.headers.get("Accept", "")
    return request.headers.get("HX-Request") or "application/json" in accept


def _payment_error_response(request, message, *, status=400):
    if _expects_json(request):
        return JsonResponse({"error": message}, status=status)
    messages.error(request, message)
    return redirect("orders:checkout")


def _valid_mollie_webhook_token(request):
    configured_secret = getattr(settings, "MOLLIE_WEBHOOK_SECRET", "").strip()
    if not configured_secret:
        return False

    supplied_secret = (
        request.GET.get("token")
        or request.POST.get("token")
        or request.headers.get("X-Webhook-Token", "")
    ).strip()
    return bool(supplied_secret) and compare_digest(supplied_secret, configured_secret)


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
                reverse("payments:demo_checkout", args=[order.order_number])
            ),
            "metadata": {"provider": Payment.Provider.DEMO},
        },
    )
    return payment


@require_POST
def create_payment(request):
    """Create a payment for checkout."""
    service_type = selected_service_type(request)
    store_service_type(request, service_type)
    if not online_payment_available():
        return _payment_error_response(
            request,
            "Online payments are unavailable right now. Please try again later.",
            status=503,
        )

    active_offer_id = selected_offer_id(request)
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=request.user,
        voucher_code=request.session.get("voucher_code", ""),
        offer_id=active_offer_id,
    )
    if not summary["items"]:
        return _payment_error_response(request, "Your basket is empty.")

    customer_name = request.POST.get("customer_name", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()
    customer_email = request.POST.get("customer_email", "").strip()
    special_instructions = request.POST.get("special_instructions", "").strip()
    delivery_details = extract_delivery_details(request.POST)

    try:
        validate_customer_details(customer_name, customer_phone)
        validate_service_details(service_type, delivery_details)
    except ValidationError as exc:
        return _payment_error_response(request, str(exc))

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
        return _payment_error_response(
            request,
            summary["voucher_error"] or "Invalid voucher code.",
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
                service_type=service_type,
                delivery_details=delivery_details,
                status=Order.OrderStatus.PENDING,
                payment_status=Order.PaymentStatus.PENDING,
            )

            if demo_payment_enabled():
                payment = _create_demo_payment(order, request)
            else:
                service = payment_service_for_provider()
                if not service:
                    raise RuntimeError("No payment provider is configured.")
                payment = service.create_payment(order, request)
    except Exception:
        logger.exception(
            "Error creating payment for order %s",
            getattr(order, "order_number", "pending"),
        )
        return _payment_error_response(
            request,
            "We could not start the payment. Your basket is still available, so please try again.",
            status=500,
        )

    clear_checkout_session(request)
    return redirect(payment.checkout_url)


def payment_return(request, order_number):
    """Handle return from checkout."""
    order = get_object_or_404(Order, order_number=order_number)
    _sync_order_payment(order, request=request)
    order.refresh_from_db()

    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:confirmation", order_number=order_number)

    return render(
        request,
        "payments/payment_status.html",
        {
            "order": order,
            "status": order.payment_status,
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

    if event_type.startswith("checkout.session.") and checkout_session_id:
        payment = StripePaymentService().update_payment_status(
            checkout_session_id,
            payload=session_payload,
            event_type=event_type,
        )
        if payment:
            PaymentLog.objects.create(
                payment=payment,
                event_type="webhook_received",
                event_data={"provider": Payment.Provider.STRIPE, "event_type": event_type},
            )

    return HttpResponse("OK", status=200)


def _mollie_webhook(request):
    if not _valid_mollie_webhook_token(request):
        logger.warning("Rejected Mollie webhook due to invalid token")
        return HttpResponse("Forbidden", status=403)

    payment_id = request.POST.get("id")
    if not payment_id:
        logger.warning("Mollie webhook received without payment ID")
        return HttpResponse("OK", status=200)

    if payment_id.startswith("demo_"):
        return HttpResponse("OK", status=200)

    logger.info("Mollie webhook received for payment: %s", payment_id)
    payment = payment_service_for_provider(Payment.Provider.MOLLIE).update_payment_status(payment_id)
    if payment:
        logger.info("Payment %s updated to %s", payment_id, payment.status)
    else:
        logger.warning("Payment %s not found", payment_id)
    return HttpResponse("OK", status=200)


@csrf_exempt
@require_POST
@rate_limit("payments-webhook", limit=120, window_seconds=60, response_type="plain")
def webhook(request):
    """Handle payment provider webhooks for the active provider."""
    provider = normalize_payment_provider(active_payment_provider())
    if provider == Payment.Provider.STRIPE:
        return _stripe_webhook(request)
    if provider == Payment.Provider.MOLLIE:
        return _mollie_webhook(request)
    return HttpResponse("Unavailable", status=503)


def payment_status_api(request, order_number):
    """API endpoint to check payment status."""
    order = get_object_or_404(Order, order_number=order_number)
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

    order = get_object_or_404(Order, order_number=order_number)
    payment = _create_demo_payment(order, request)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "pay":
            payment.status = Payment.Status.PAID
            payment.save(update_fields=["status", "updated_at"])
            order.mark_as_paid()
            return redirect("orders:confirmation", order_number=order_number)

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
