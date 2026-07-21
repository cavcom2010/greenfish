"""Customer-facing transactional notification helpers."""
from django.conf import settings
from django.utils import timezone

from apps.core.models import NotificationEvent, SiteSettings
from apps.sms.models import SMSMessage, SMSSettings


ORDER_CONFIRMED = "order_confirmed"
ORDER_READY = "order_ready"
ORDER_OUT_FOR_DELIVERY = "order_out_for_delivery"
ORDER_DELIVERED = "order_delivered"
ORDER_ISSUE_RECEIVED = "order_issue_received"
ORDER_REFUND_PROCESSED = "order_refund_processed"
LARGE_ORDER_REQUEST_RECEIVED = "large_order_request_received"


def _shop():
    return SiteSettings.get()


def _tracking_url(order):
    base_url = getattr(settings, "SHOP_URL", "").rstrip("/")
    path = f"/orders/track/{order.order_number}/?t={order.public_access_token}"
    return f"{base_url}{path}" if base_url else path


def _customer_notifications_enabled(order=None, user=None):
    user = user or getattr(order, "user", None)
    if not user:
        return True
    profile = getattr(user, "profile", None)
    return bool(getattr(profile, "notifications_enabled", True))


def _order_email(order):
    return (order.customer_email or getattr(order.user, "email", "") or "").strip()


def _order_phone(order):
    return (order.customer_phone or getattr(order.user, "phone_number", "") or "").strip()


def _order_event_exists(order, *, channel, event_type, recipient=""):
    queryset = NotificationEvent.objects.filter(order=order, channel=channel, event_type=event_type)
    if recipient:
        queryset = queryset.filter(recipient=recipient)
    return queryset.exclude(status=NotificationEvent.Status.CANCELLED).exists()


def _sms_record_exists(order, message_type):
    return SMSMessage.objects.filter(order=order, message_type=message_type).exists()


def _enqueue_email_once(order, *, event_type, subject, text_body, html_body=""):
    email = _order_email(order)
    if not email or not _customer_notifications_enabled(order):
        return None
    if _order_event_exists(order, channel=NotificationEvent.Channel.EMAIL, event_type=event_type, recipient=email):
        return None
    return NotificationEvent.objects.create(
        channel=NotificationEvent.Channel.EMAIL,
        event_type=event_type,
        recipient=email,
        payload={"subject": subject, "message": text_body, "html_body": html_body},
        order=order,
        next_attempt_at=timezone.now(),
    )


def _status_email_body(order, heading, detail):
    tracking_url = _tracking_url(order)
    text = (
        f"{heading}\n\n"
        f"Order: {order.order_number}\n"
        f"{detail}\n"
        f"Track your order: {tracking_url}"
    )
    html = (
        f"<p><strong>{heading}</strong></p>"
        f"<p><strong>Order:</strong> {order.order_number}</p>"
        f"<p>{detail}</p>"
        f"<p><a href=\"{tracking_url}\">Track your order</a></p>"
    )
    return text, html


def _enqueue_sms_once(order, *, event_type, message_type, message, toggle_field):
    sms_settings = SMSSettings.get()
    if not sms_settings.enabled or not getattr(sms_settings, toggle_field, False):
        return None
    phone = _order_phone(order)
    if not phone or not _customer_notifications_enabled(order):
        return None
    if _order_event_exists(order, channel=NotificationEvent.Channel.SMS, event_type=event_type, recipient=phone):
        return None
    if _sms_record_exists(order, message_type):
        return None
    return NotificationEvent.objects.create(
        channel=NotificationEvent.Channel.SMS,
        event_type=event_type,
        recipient=phone,
        payload={"message_type": message_type, "message": message},
        order=order,
        next_attempt_at=timezone.now(),
    )


def enqueue_order_confirmed(order):
    """Queue customer receipt/confirmation notifications after payment succeeds."""
    if order.payment_status != order.PaymentStatus.PAID:
        return
    from django.template.loader import render_to_string

    from apps.payments.models import ManualPaymentReceipt

    shop = _shop()
    tracking_url = _tracking_url(order)
    subject = f"{shop.shop_name}: order {order.order_number} confirmed"

    payment = getattr(order, "payment", None)
    payment_method_label = "Online (Stripe)"
    if payment:
        if hasattr(payment, "manual_receipt") and payment.manual_receipt:
            payment_method_label = payment.manual_receipt.get_method_display()
        elif payment.payment_method_label:
            payment_method_label = payment.payment_method_label

    html = render_to_string(
        "orders/email_receipt.html",
        {
            "order": order,
            "items": list(order.items.all()),
            "payment_method": payment_method_label,
            "tracking_url": tracking_url,
            "site_settings": shop,
        },
    )
    text = (
        f"Thanks for your order from {shop.shop_name}.\n\n"
        f"Order: {order.order_number}\n"
        f"Total: £{order.total_amount}\n"
        f"Track your order: {tracking_url}"
    )
    _enqueue_email_once(order, event_type=ORDER_CONFIRMED, subject=subject, text_body=text, html_body=html)
    _enqueue_sms_once(
        order,
        event_type=ORDER_CONFIRMED,
        message_type=SMSMessage.MessageType.ORDER_CONFIRMED,
        message=f"Your order #{order.order_number} for £{order.total_amount} is confirmed. Track: {tracking_url}",
        toggle_field="send_order_confirmed",
    )


def enqueue_order_ready(order):
    """Queue pickup-ready notifications for paid pickup orders."""
    if order.payment_status != order.PaymentStatus.PAID or order.is_delivery:
        return
    shop = _shop()
    detail = f"Your order is ready for collection at {shop.shop_name}."
    email_text, email_html = _status_email_body(order, "Your order is ready for collection", detail)
    _enqueue_email_once(
        order,
        event_type=ORDER_READY,
        subject=f"{shop.shop_name}: order {order.order_number} is ready",
        text_body=email_text,
        html_body=email_html,
    )
    text = f"Your order #{order.order_number} is ready for collection at {shop.shop_name}."
    _enqueue_sms_once(
        order,
        event_type=ORDER_READY,
        message_type=SMSMessage.MessageType.ORDER_READY,
        message=text,
        toggle_field="send_order_ready",
    )


def enqueue_order_out_for_delivery(order):
    """Queue dispatch notifications for paid delivery orders."""
    if order.payment_status != order.PaymentStatus.PAID or not order.is_delivery:
        return
    shop = _shop()
    tracking_url = _tracking_url(order)
    detail = "Your order has left the shop and is on the way."
    email_text, email_html = _status_email_body(order, "Your order is on the way", detail)
    _enqueue_email_once(
        order,
        event_type=ORDER_OUT_FOR_DELIVERY,
        subject=f"{shop.shop_name}: order {order.order_number} is on the way",
        text_body=email_text,
        html_body=email_html,
    )
    text = f"Your order #{order.order_number} is out for delivery. Track: {tracking_url}"
    _enqueue_sms_once(
        order,
        event_type=ORDER_OUT_FOR_DELIVERY,
        message_type=SMSMessage.MessageType.ORDER_OUT_FOR_DELIVERY,
        message=text,
        toggle_field="send_order_ready",
    )


def enqueue_order_delivered(order):
    """Queue optional delivered notifications for paid delivery orders."""
    if order.payment_status != order.PaymentStatus.PAID or not order.is_delivery:
        return
    shop = _shop()
    detail = f"Your order has been delivered. Thanks for ordering with {shop.shop_name}."
    email_text, email_html = _status_email_body(order, "Your order has been delivered", detail)
    _enqueue_email_once(
        order,
        event_type=ORDER_DELIVERED,
        subject=f"{shop.shop_name}: order {order.order_number} delivered",
        text_body=email_text,
        html_body=email_html,
    )
    text = f"Your order #{order.order_number} has been delivered. Thanks for ordering with {shop.shop_name}."
    _enqueue_sms_once(
        order,
        event_type=ORDER_DELIVERED,
        message_type=SMSMessage.MessageType.ORDER_DELIVERED,
        message=text,
        toggle_field="send_order_delivered",
    )


def enqueue_order_status_notification(order_id, status):
    """Load an order and queue the correct status notification."""
    from apps.orders.models import Order

    order = Order.objects.select_related("user").filter(pk=order_id).first()
    if not order:
        return
    if status == Order.OrderStatus.READY:
        enqueue_order_ready(order)
    elif status == Order.OrderStatus.OUT_FOR_DELIVERY:
        enqueue_order_out_for_delivery(order)
    elif status == Order.OrderStatus.COMPLETED:
        enqueue_order_delivered(order)


def enqueue_order_confirmed_by_id(order_id):
    from apps.orders.models import Order

    order = Order.objects.select_related("user").filter(pk=order_id).first()
    if order:
        enqueue_order_confirmed(order)


def enqueue_order_issue_received(issue):
    order = issue.order
    issue_label = issue.get_issue_type_display()
    subject = f"{_shop().shop_name}: issue received for {order.order_number}"
    text = (
        f"We have received your {issue_label.lower()} report for order {order.order_number}.\n"
        "The team will review it and contact you if more information is needed."
    )
    _enqueue_email_once(order, event_type=ORDER_ISSUE_RECEIVED, subject=subject, text_body=text)


def enqueue_refund_processed(refund_request):
    order = refund_request.payment.order
    amount_label = f"£{refund_request.amount}" if refund_request.amount else "the eligible amount"
    subject = f"{_shop().shop_name}: refund processed for {order.order_number}"
    text = (
        f"Your refund for order {order.order_number} has been processed for {amount_label}.\n"
        "Your payment provider may take a few working days to show it in your account."
    )
    _enqueue_email_once(order, event_type=ORDER_REFUND_PROCESSED, subject=subject, text_body=text)


def enqueue_large_order_request_received(large_order):
    email = (large_order.email or "").strip()
    if not email or not _customer_notifications_enabled(user=large_order.user):
        return None
    shop = _shop()
    subject = f"{shop.shop_name}: large order request received"
    text = (
        f"Thanks {large_order.name}, we have received your large order request.\n"
        "The team will review availability, timing, and payment before confirming."
    )
    return NotificationEvent.objects.create(
        channel=NotificationEvent.Channel.EMAIL,
        event_type=LARGE_ORDER_REQUEST_RECEIVED,
        recipient=email,
        payload={"subject": subject, "message": text, "large_order_request_id": large_order.pk},
        next_attempt_at=timezone.now(),
    )
