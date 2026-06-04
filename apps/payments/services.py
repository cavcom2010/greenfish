"""
Payment provider services.
"""
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from mollie.api.client import Client
from mollie.api.error import Error as MollieError

from apps.orders.models import Order
from config.settings.payment_credentials import (
    mollie_credentials_configured,
    stripe_credentials_configured,
)

from .models import ManualPaymentReceipt, Payment, PaymentLog, RefundRequest

logger = logging.getLogger(__name__)

try:
    import stripe
    from stripe import error as stripe_error
except Exception:  # pragma: no cover - dependency is installed in runtime, this is a safety net.
    stripe = None
    stripe_error = None


def normalize_payment_provider(raw_provider):
    """Return a supported payment provider identifier."""
    value = (raw_provider or "").strip().lower()
    valid_providers = {choice for choice, _ in Payment.Provider.choices}
    if value in valid_providers:
        return value
    return Payment.Provider.STRIPE


def active_payment_provider():
    """Return the configured online payment provider."""
    return normalize_payment_provider(getattr(settings, "PAYMENT_PROVIDER", Payment.Provider.STRIPE))


def payment_provider_configured(provider=None):
    """Return whether the requested payment provider has usable credentials."""
    provider = normalize_payment_provider(provider or active_payment_provider())

    if provider == Payment.Provider.STRIPE:
        return stripe_credentials_configured(
            getattr(settings, "STRIPE_SECRET_KEY", ""),
            getattr(settings, "STRIPE_WEBHOOK_SECRET", ""),
        )

    if provider == Payment.Provider.MOLLIE:
        return mollie_credentials_configured(
            getattr(settings, "MOLLIE_API_KEY", ""),
            getattr(settings, "MOLLIE_WEBHOOK_SECRET", ""),
        )

    return False


def payment_fallback_enabled():
    """Return whether unpaid fallback orders are allowed."""
    return bool(getattr(settings, "PAYMENT_FALLBACK_ENABLED", True))


def payment_fallback_hold_minutes():
    """Return the unpaid fallback hold window in minutes."""
    try:
        return max(1, int(getattr(settings, "PAYMENT_FALLBACK_HOLD_MINUTES", 15)))
    except (TypeError, ValueError):
        return 15


def payment_service_for_provider(provider=None):
    """Return the service instance for the requested provider."""
    provider = normalize_payment_provider(provider or active_payment_provider())

    if provider == Payment.Provider.STRIPE:
        return StripePaymentService()
    if provider == Payment.Provider.MOLLIE:
        return MolliePaymentService()
    return None


def payment_service_for_payment(payment):
    """Return the provider service that owns a local payment record."""
    if not payment or payment.is_demo or payment.is_offline_pending:
        return None
    return payment_service_for_provider(payment.provider)


def refresh_payment_status(payment, *, external_id=None, payload=None, event_type=""):
    """Refresh a local payment from its remote provider."""
    service = payment_service_for_payment(payment)
    if not service:
        return payment

    payment_reference = external_id or payment.external_payment_id or payment.mollie_payment_id
    if not payment_reference:
        return payment
    return service.update_payment_status(payment_reference, payload=payload, event_type=event_type)


def process_refund_request(refund_request):
    """Process a staff refund request through the payment's provider service."""
    refund_request = RefundRequest.objects.select_related("payment", "payment__order").get(pk=refund_request.pk)
    if refund_request.status != RefundRequest.Status.REQUESTED:
        return refund_request

    payment = refund_request.payment
    if payment.status != Payment.Status.PAID:
        refund_request.status = RefundRequest.Status.FAILED
        refund_request.error_message = "Only paid payments can be refunded."
        refund_request.processed_at = timezone.now()
        refund_request.save(update_fields=["status", "error_message", "processed_at"])
        return refund_request

    service = payment_service_for_payment(payment)
    if not service:
        refund_request.status = RefundRequest.Status.FAILED
        refund_request.error_message = "No refund-capable payment service is configured."
        refund_request.processed_at = timezone.now()
        refund_request.save(update_fields=["status", "error_message", "processed_at"])
        return refund_request

    success = service.refund_payment(payment, amount=refund_request.amount)
    refund_request.processed_at = timezone.now()
    if success:
        refund_request.status = RefundRequest.Status.SUCCEEDED
        refund_request.provider_reference = payment.payment_reference
    else:
        refund_request.status = RefundRequest.Status.FAILED
        refund_request.error_message = "Provider refund failed. Check payment logs."
    refund_request.save(update_fields=["status", "provider_reference", "error_message", "processed_at"])
    return refund_request


def _minor_units(amount):
    quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((quantized * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _money(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid payment amount.")


def _reject_full_card_number(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) >= 12:
        raise ValueError("Do not store full card numbers. Use the receipt or auth code only.")


def _request_ip(request):
    if not request:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _user_agent(request):
    if not request:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:500]


def _serialize_stripe_object(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


def _get_payment(provider, external_payment_id):
    query = Q(provider=provider, external_payment_id=external_payment_id)
    if provider == Payment.Provider.MOLLIE:
        query |= Q(mollie_payment_id=external_payment_id)
    return Payment.objects.select_related("order").filter(query).first()


def _log_payment_event(payment, event_type, event_data):
    PaymentLog.objects.create(
        payment=payment,
        event_type=event_type,
        event_data=event_data,
    )


def create_offline_pending_payment(order, request, *, reason="online_payment_unavailable"):
    """Create a fallback payment record that must be paid in shop/by phone."""
    hold_minutes = payment_fallback_hold_minutes()
    expires_at = timezone.now() + timezone.timedelta(minutes=hold_minutes)
    payment_id = f"offline_{uuid.uuid4().hex[:12]}"
    checkout_url = request.build_absolute_uri(
        reverse("payments:return", args=[order.order_number])
    )
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.OFFLINE_PENDING,
        external_payment_id=payment_id,
        amount=order.total_amount,
        currency=getattr(settings, "CURRENCY", "GBP"),
        status=Payment.Status.PENDING,
        checkout_url=checkout_url,
        expires_at=expires_at,
        metadata={
            "provider": Payment.Provider.OFFLINE_PENDING,
            "reason": reason,
            "hold_minutes": hold_minutes,
            "instructions": "Customer must call or visit the shop to pay before preparation starts.",
        },
    )
    _log_payment_event(
        payment,
        "offline_pending_created",
        {
            "provider": Payment.Provider.OFFLINE_PENDING,
            "reason": reason,
            "expires_at": expires_at.isoformat(),
        },
    )
    return payment


def record_manual_payment(
    payment,
    *,
    actor=None,
    method="",
    amount_received=None,
    reference_code="",
    notes="",
    request=None,
):
    """Record manual payment evidence, then release the order to the kitchen."""
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    method = (method or "").strip()
    valid_methods = {choice for choice, _ in ManualPaymentReceipt.Method.choices}
    if method not in valid_methods:
        raise ValueError("Select how the payment was taken.")
    if payment.provider != Payment.Provider.OFFLINE_PENDING:
        raise ValueError("This order is not awaiting shop payment.")
    if payment.status != Payment.Status.PENDING:
        raise ValueError("This payment is not pending.")
    if ManualPaymentReceipt.objects.filter(payment=payment).exists():
        raise ValueError("This payment has already been recorded.")

    amount_due = _money(payment.amount)
    amount_received = _money(amount_received)
    if amount_received < amount_due:
        raise ValueError("Amount received must be at least the order total.")

    if method in {ManualPaymentReceipt.Method.CARD_TERMINAL, ManualPaymentReceipt.Method.PHONE_CARD}:
        if amount_received != amount_due:
            raise ValueError("Card and phone payments must match the order total exactly.")
        change_given = Decimal("0.00")
    else:
        change_given = amount_received - amount_due

    reference_code = (reference_code or "").strip()
    notes = (notes or "").strip()
    if not reference_code:
        raise ValueError("Receipt or auth reference is required.")
    _reject_full_card_number(reference_code)
    _reject_full_card_number(notes)

    receipt = ManualPaymentReceipt.objects.create(
        payment=payment,
        method=method,
        amount_due=amount_due,
        amount_received=amount_received,
        change_given=change_given,
        reference_code=reference_code,
        notes=notes,
        recorded_by=actor if getattr(actor, "is_authenticated", False) else None,
        request_ip=_request_ip(request),
        user_agent=_user_agent(request),
    )

    payment.status = Payment.Status.PAID
    payment.paid_at = payment.paid_at or timezone.now()
    payment.external_payment_method = method
    metadata = payment.metadata or {}
    metadata.update(
        {
            "marked_paid_by": getattr(actor, "email", "") or getattr(actor, "pk", None),
            "marked_paid_at": timezone.now().isoformat(),
            "manual_receipt_id": receipt.pk,
            "manual_payment_method": method,
            "manual_amount_received": str(amount_received),
            "manual_change_given": str(change_given),
            "manual_reference_code": reference_code,
        }
    )
    payment.metadata = metadata
    payment.save(update_fields=["status", "paid_at", "external_payment_method", "metadata", "updated_at"])
    payment.order.mark_as_paid(changed_by=actor if getattr(actor, "is_authenticated", False) else None)
    _log_payment_event(
        payment,
        "offline_payment_marked_paid",
        {
            "actor_id": getattr(actor, "pk", None),
            "actor_email": getattr(actor, "email", ""),
            "manual_receipt_id": receipt.pk,
            "method": method,
            "amount_due": str(amount_due),
            "amount_received": str(amount_received),
            "change_given": str(change_given),
            "reference_code": reference_code,
            "request_ip": receipt.request_ip,
            "user_agent": receipt.user_agent,
        },
    )
    return payment


def mark_offline_payment_paid(payment, *, actor=None, **payment_evidence):
    """Compatibility wrapper requiring manual payment evidence."""
    if not payment_evidence:
        raise ValueError("Payment evidence is required before marking this order paid.")
    return record_manual_payment(payment, actor=actor, **payment_evidence)


def expire_offline_pending_payment(payment, *, reason="Payment not received within the hold window."):
    """Expire an unpaid fallback payment and cancel the related order."""
    payment.status = Payment.Status.EXPIRED
    payment.save(update_fields=["status", "updated_at"])

    order = payment.order
    order.payment_status = Order.PaymentStatus.FAILED
    if reason and reason != order.cancel_reason:
        order.cancel_reason = reason
        order.save(update_fields=["payment_status", "cancel_reason", "updated_at"])
    else:
        order.save(update_fields=["payment_status", "updated_at"])
    if order.status == Order.OrderStatus.PENDING:
        order.update_status(Order.OrderStatus.CANCELLED)
    else:
        from apps.orders.fulfilment import release_fulfilment_slot
        from apps.orders.inventory import release_order_stock

        release_fulfilment_slot(order)
        release_order_stock(order)

    _log_payment_event(
        payment,
        "offline_payment_expired",
        {"reason": reason},
    )
    return payment


def _apply_local_payment_state(
    payment,
    *,
    new_status,
    provider_status="",
    payment_method="",
    metadata=None,
    paid_at=None,
):
    """Apply a provider status update to the local payment and order records."""
    old_status = payment.status
    payment.status = new_status

    if payment_method:
        payment.external_payment_method = payment_method
        if payment.provider == Payment.Provider.MOLLIE:
            payment.mollie_payment_method = payment_method

    if metadata is not None:
        payment.metadata = metadata

    if payment.status == Payment.Status.PAID:
        payment.paid_at = paid_at or payment.paid_at or timezone.now()
        payment.order.mark_as_paid()
    elif payment.status == Payment.Status.REFUNDED:
        payment.order.payment_status = Order.PaymentStatus.REFUNDED
        payment.order.save(update_fields=["payment_status", "updated_at"])
    elif payment.status in {Payment.Status.FAILED, Payment.Status.EXPIRED, Payment.Status.CANCELLED}:
        payment.order.payment_status = Order.PaymentStatus.FAILED
        if payment.order.status == Order.OrderStatus.PENDING:
            payment.order.save(update_fields=["payment_status", "updated_at"])
            payment.order.update_status(Order.OrderStatus.CANCELLED)
        else:
            payment.order.save(update_fields=["payment_status", "updated_at"])
            from apps.orders.fulfilment import release_fulfilment_slot
            from apps.orders.inventory import release_order_stock

            release_fulfilment_slot(payment.order)
            release_order_stock(payment.order)

    payment.save()

    if old_status != payment.status:
        _log_payment_event(
            payment,
            "status_changed",
            {
                "provider": payment.provider,
                "old_status": old_status,
                "new_status": payment.status,
                "provider_status": provider_status,
            },
        )

    return payment


class StripePaymentService:
    """Hosted Stripe Checkout integration."""

    def __init__(self):
        if stripe is None:
            raise ImproperlyConfigured("The stripe package is required for Stripe payments.")
        stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "").strip()

    def create_payment(self, order, request):
        """Create a Stripe Checkout Session for an order."""
        if not getattr(settings, "STRIPE_SECRET_KEY", "").strip():
            raise ImproperlyConfigured("STRIPE_SECRET_KEY is not configured.")

        base_url = f"{request.scheme}://{request.get_host()}"
        redirect_url = f"{base_url}{reverse('payments:return', args=[order.order_number])}"

        line_item_description = (
            f"{order.items.count()} line item(s) • {'Delivery' if order.is_delivery else 'Pickup'}"
        )
        session_kwargs = {
            "mode": "payment",
            "success_url": f"{redirect_url}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{redirect_url}?cancelled=1",
            "line_items": [
                {
                    "price_data": {
                        "currency": getattr(settings, "CURRENCY", "GBP").lower(),
                        "product_data": {
                            "name": f"Order {order.order_number}",
                            "description": line_item_description,
                        },
                        "unit_amount": _minor_units(order.total_amount),
                    },
                    "quantity": 1,
                }
            ],
            "metadata": {
                "order_number": order.order_number,
                "order_id": str(order.id),
                "service_type": order.service_type,
                "customer_name": order.customer_name,
            },
            "payment_intent_data": {
                "metadata": {
                    "order_number": order.order_number,
                    "order_id": str(order.id),
                }
            },
        }
        if order.customer_email:
            session_kwargs["customer_email"] = order.customer_email

        try:
            stripe_session = stripe.checkout.Session.create(**session_kwargs)
        except Exception as exc:
            logger.error("Stripe error creating checkout session: %s", exc)
            raise

        session_data = _serialize_stripe_object(stripe_session)
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.STRIPE,
            external_payment_id=stripe_session["id"],
            amount=order.total_amount,
            currency=getattr(settings, "CURRENCY", "GBP"),
            status=Payment.Status.PENDING,
            checkout_url=session_data.get("url", ""),
            metadata=session_data,
        )

        _log_payment_event(
            payment,
            "payment_created",
            {
                "provider": Payment.Provider.STRIPE,
                "checkout_session_id": payment.external_payment_id,
            },
        )
        return payment

    def get_payment(self, checkout_session_id):
        """Get a checkout session from Stripe."""
        if not getattr(settings, "STRIPE_SECRET_KEY", "").strip():
            return None
        return stripe.checkout.Session.retrieve(checkout_session_id)

    def update_payment_status(self, checkout_session_id, payload=None, event_type=""):
        """Update local payment status from Stripe Checkout session state."""
        payment = _get_payment(Payment.Provider.STRIPE, checkout_session_id)
        if not payment:
            logger.warning("Payment not found for Stripe session %s", checkout_session_id)
            return None

        session_data = _serialize_stripe_object(payload) if payload else _serialize_stripe_object(
            self.get_payment(checkout_session_id)
        )
        if not session_data:
            return None

        session_status = (session_data.get("status") or "").lower()
        payment_status = (session_data.get("payment_status") or "").lower()
        method_types = session_data.get("payment_method_types") or []
        method_name = method_types[0] if method_types else ""

        new_status = Payment.Status.PENDING
        if payment_status in {"paid", "no_payment_required"}:
            new_status = Payment.Status.PAID
        elif event_type == "checkout.session.async_payment_failed":
            new_status = Payment.Status.FAILED
        elif session_status == "expired" or event_type == "checkout.session.expired":
            new_status = Payment.Status.EXPIRED

        return _apply_local_payment_state(
            payment,
            new_status=new_status,
            provider_status=f"{session_status}:{payment_status}".strip(":"),
            payment_method=method_name,
            metadata=session_data,
        )

    def refund_payment(self, payment, amount=None):
        """Refund a Stripe payment intent when one exists on the checkout session."""
        payment_intent = (payment.metadata or {}).get("payment_intent")
        if not payment_intent:
            return False

        refund_kwargs = {"payment_intent": payment_intent}
        if amount is not None:
            refund_kwargs["amount"] = _minor_units(amount)

        try:
            stripe.Refund.create(**refund_kwargs)
        except Exception as exc:
            logger.error("Stripe error refunding payment %s: %s", payment.payment_reference, exc)
            return False

        _apply_local_payment_state(
            payment,
            new_status=Payment.Status.REFUNDED,
            provider_status="refunded",
            metadata=payment.metadata,
        )
        _log_payment_event(
            payment,
            "refunded",
            {
                "provider": Payment.Provider.STRIPE,
                "amount": str(amount) if amount is not None else "full",
            },
        )
        return True


class MolliePaymentService:
    """Service for handling Mollie payments."""

    def __init__(self):
        self.client = Client()
        api_key = getattr(settings, "MOLLIE_API_KEY", "")
        if api_key:
            self.client.set_api_key(api_key)

    def create_payment(self, order, request):
        """Create a new Mollie payment for an order."""
        try:
            base_url = f"{request.scheme}://{request.get_host()}"
            redirect_url = f"{base_url}{reverse('payments:return', args=[order.order_number])}"
            webhook_url = f"{base_url}{reverse('payments:webhook')}"
            webhook_secret = getattr(settings, "MOLLIE_WEBHOOK_SECRET", "").strip()
            if webhook_secret:
                webhook_url = f"{webhook_url}?{urlencode({'token': webhook_secret})}"

            payment_data = {
                "amount": {
                    "currency": getattr(settings, "CURRENCY", "GBP"),
                    "value": f"{order.total_amount:.2f}",
                },
                "description": f"Order {order.order_number} - {order.customer_name}",
                "redirectUrl": redirect_url,
                "webhookUrl": webhook_url,
                "metadata": {
                    "order_number": order.order_number,
                    "order_id": order.id,
                    "customer_name": order.customer_name,
                    "customer_email": order.customer_email,
                },
            }

            mollie_payment = self.client.payments.create(payment_data)
            payment = Payment.objects.create(
                order=order,
                provider=Payment.Provider.MOLLIE,
                external_payment_id=mollie_payment["id"],
                mollie_payment_id=mollie_payment["id"],
                amount=order.total_amount,
                currency=getattr(settings, "CURRENCY", "GBP"),
                status=Payment.Status.PENDING,
                checkout_url=mollie_payment["checkoutUrl"],
                metadata=mollie_payment,
            )

            order.mollie_payment_id = mollie_payment["id"]
            order.save(update_fields=["mollie_payment_id", "updated_at"])

            _log_payment_event(
                payment,
                "payment_created",
                {
                    "provider": Payment.Provider.MOLLIE,
                    "mollie_payment_id": mollie_payment["id"],
                },
            )
            return payment

        except MollieError as exc:
            logger.error("Mollie error creating payment: %s", exc)
            raise
        except Exception as exc:
            logger.error("Error creating Mollie payment: %s", exc)
            raise

    def get_payment(self, mollie_payment_id):
        """Get payment details from Mollie."""
        if not getattr(settings, "MOLLIE_API_KEY", ""):
            return None
        try:
            return self.client.payments.get(mollie_payment_id)
        except MollieError as exc:
            logger.error("Mollie error getting payment: %s", exc)
            return None

    def update_payment_status(self, mollie_payment_id, payload=None, event_type=""):
        """Update local payment status from Mollie."""
        payment = _get_payment(Payment.Provider.MOLLIE, mollie_payment_id)
        if not payment:
            logger.warning("Payment not found: %s", mollie_payment_id)
            return None

        mollie_payment = payload or self.get_payment(mollie_payment_id)
        if not mollie_payment:
            return None

        status_map = {
            "pending": Payment.Status.PENDING,
            "authorized": Payment.Status.AUTHORIZED,
            "paid": Payment.Status.PAID,
            "failed": Payment.Status.FAILED,
            "expired": Payment.Status.EXPIRED,
            "canceled": Payment.Status.CANCELLED,
            "refunded": Payment.Status.REFUNDED,
        }
        mollie_status = mollie_payment.get("status", "pending")
        return _apply_local_payment_state(
            payment,
            new_status=status_map.get(mollie_status, Payment.Status.PENDING),
            provider_status=mollie_status,
            payment_method=mollie_payment.get("method", ""),
            metadata=mollie_payment,
            paid_at=parse_datetime(mollie_payment.get("paidAt", "")) or None,
        )

    def refund_payment(self, payment, amount=None):
        """Refund a payment."""
        try:
            refund_data = {}
            if amount:
                refund_data["amount"] = {
                    "currency": payment.currency,
                    "value": f"{amount:.2f}",
                }

            self.client.payment_refunds.with_parent_id(
                payment.mollie_payment_id or payment.external_payment_id
            ).create(refund_data)

            _apply_local_payment_state(
                payment,
                new_status=Payment.Status.REFUNDED,
                provider_status="refunded",
                metadata=payment.metadata,
            )
            _log_payment_event(
                payment,
                "refunded",
                {
                    "provider": Payment.Provider.MOLLIE,
                    "amount": str(amount) if amount else "full",
                },
            )
            return True

        except MollieError as exc:
            logger.error("Mollie error refunding payment: %s", exc)
            return False
