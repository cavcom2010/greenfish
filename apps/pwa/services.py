"""
PWA services - Push notification sending.

This module handles sending push notifications to subscribed users.

Note: In production, you would use a library like pywebpush:
    pip install pywebpush

For now, this is a placeholder showing the structure.
"""
import json
import logging

from django.conf import settings

from .models import PushSubscription

logger = logging.getLogger(__name__)


def send_push_notification(subscription, title, body, data=None, actions=None):
    """
    Send a push notification to a specific subscription.
    
    Args:
        subscription: PushSubscription object
        title: Notification title
        body: Notification body
        data: Additional data to send (dict)
        actions: Action buttons (list of dicts)
    
    Returns:
        bool: Success status
    """
    try:
        # In production, use pywebpush:
        # from pywebpush import webpush, WebPushException
        # webpush(
        #     subscription_info={
        #         'endpoint': subscription.endpoint,
        #         'keys': {
        #             'p256dh': subscription.p256dh,
        #             'auth': subscription.auth
        #         }
        #     },
        #     data=json.dumps({
        #         'title': title,
        #         'body': body,
        #         'data': data or {},
        #         'actions': actions or []
        #     }),
        #     vapid_private_key=settings.VAPID_PRIVATE_KEY,
        #     vapid_claims={
        #         'sub': f'mailto:{settings.DEFAULT_FROM_EMAIL}'
        #     }
        # )
        
        logger.info(f"Would send push notification: {title} - {body}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send push notification: {e}")
        return False


def notify_order_status(order, status_message):
    """
    Send order status update to customer.
    
    Args:
        order: Order object
        status_message: Human-readable status message
    """
    if not order.user:
        return  # Can't notify anonymous users without push
    
    # Get active subscriptions for user
    subscriptions = PushSubscription.objects.filter(
        user=order.user,
        is_active=True
    )
    
    if not subscriptions.exists():
        return
    
    # Prepare notification data
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
    
    # Send to all user's devices
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
