"""
PWA services — Web Push notification sending via pywebpush + VAPID.

Configure VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY in the environment. Generate a
keypair with:  python manage.py generate_vapid_keys
"""
import json
import logging

from django.conf import settings

from .models import PushSubscription

logger = logging.getLogger(__name__)

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover - optional dependency safety net.
    webpush = None
    WebPushException = None


def push_configured():
    """Return whether VAPID keys are available for sending push messages."""
    return bool(
        webpush is not None
        and getattr(settings, "VAPID_PRIVATE_KEY", "").strip()
        and getattr(settings, "VAPID_PUBLIC_KEY", "").strip()
    )


def _vapid_claims():
    contact = (
        getattr(settings, "VAPID_ADMIN_EMAIL", "")
        or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or "admin@example.com"
    )
    return {"sub": f"mailto:{contact}"}


def send_push_notification(subscription, title, body, data=None, actions=None):
    """Send a push notification to a specific subscription.

    Returns True on success. Dead subscriptions (404/410 from the push
    service) are deactivated so they are never retried.
    """
    if not push_configured():
        logger.debug("Push not configured; skipping notification '%s'", title)
        return False

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "data": data or {},
            "actions": actions or [],
        }
    )

    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth,
                },
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims=_vapid_claims(),
            timeout=10,
        )
        return True
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            PushSubscription.objects.filter(pk=subscription.pk).update(is_active=False)
            logger.info("Deactivated dead push subscription %s (HTTP %s)", subscription.pk, status_code)
        else:
            logger.warning("Push delivery failed for subscription %s: %s", subscription.pk, exc)
        return False
    except Exception:
        logger.exception("Unexpected error sending push notification")
        return False


def notify_order_status(order, status_message):
    """
    Send order status update to customer.

    Args:
        order: Order object
        status_message: Human-readable status message
    """
    if not order or not order.user:
        return  # Can't notify anonymous users without push

    subscriptions = PushSubscription.objects.filter(
        user=order.user,
        is_active=True
    )

    if not subscriptions.exists():
        return

    notification_data = {
        'title': f'Order #{order.order_number} Update',
        'body': status_message,
        'data': {
            'orderNumber': order.order_number,
            'url': f'/orders/track/{order.order_number}/'
        },
        'actions': [
            {'action': 'view', 'title': 'View Order'}
        ]
    }

    for subscription in subscriptions:
        send_push_notification(
            subscription,
            notification_data['title'],
            notification_data['body'],
            notification_data['data'],
            notification_data['actions']
        )


def notify_order_confirmed(order):
    """Send order confirmation notification."""
    notify_order_status(order, f'Your order for £{order.total_amount} has been confirmed!')


def notify_order_ready(order):
    """Send order ready notification."""
    notify_order_status(order, 'Your order is ready for pickup!')


def notify_order_out_for_delivery(order):
    """Send order dispatch notification."""
    notify_order_status(order, 'Your order is on the way.')


def notify_order_delivered(order):
    """Send order delivered notification."""
    notify_order_status(order, 'Your order has been delivered.')


def broadcast_notification(title, body, data=None):
    """
    Send notification to all subscribed users.
    Use sparingly for important announcements only.
    """
    subscriptions = PushSubscription.objects.filter(is_active=True)

    for subscription in subscriptions:
        send_push_notification(subscription, title, body, data)
