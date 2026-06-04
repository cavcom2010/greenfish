"""SMS signals for automatic notifications."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order

from apps.core.models import NotificationEvent
from apps.core.notifications import enqueue_notification

from .models import SMSMessage, SMSSettings


@receiver(post_save, sender=Order)
def send_order_sms_notifications(sender, instance, created, **kwargs):
    """Send SMS notifications on order status changes."""
    sms_settings = SMSSettings.get()
    if not sms_settings.enabled:
        return

    def enqueue(message_type, message):
        phone = instance.customer_phone or (instance.user.phone_number if instance.user else "")
        if not phone:
            return
        enqueue_notification(
            channel=NotificationEvent.Channel.SMS,
            event_type=message_type,
            recipient=phone,
            payload={"message_type": message_type, "message": message},
            order=instance,
        )
    
    # Send confirmation on new order
    if created:
        enqueue(
            SMSMessage.MessageType.ORDER_CONFIRMED,
            f"Your order #{instance.order_number} for £{instance.total_amount} is confirmed.",
        )
        return
    
    # Send ready notification when status changes to ready.
    if instance.status == Order.OrderStatus.READY and not instance.is_delivery:
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_READY
        ).exists()
        
        if not already_sent:
            enqueue(
                SMSMessage.MessageType.ORDER_READY,
                f"Your order #{instance.order_number} is ready for collection.",
            )
        return

    if instance.status == Order.OrderStatus.OUT_FOR_DELIVERY:
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_OUT_FOR_DELIVERY,
        ).exists()

        if not already_sent:
            enqueue(
                SMSMessage.MessageType.ORDER_OUT_FOR_DELIVERY,
                f"Your order #{instance.order_number} is out for delivery.",
            )
        return

    if instance.status == Order.OrderStatus.COMPLETED and instance.is_delivery:
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_DELIVERED,
        ).exists()

        if not already_sent:
            enqueue(
                SMSMessage.MessageType.ORDER_DELIVERED,
                f"Your order #{instance.order_number} has been delivered.",
            )
