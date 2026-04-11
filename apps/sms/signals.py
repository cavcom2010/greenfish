"""SMS signals for automatic notifications."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order

from .models import SMSMessage, SMSSettings
from .services import (
    send_order_confirmation,
    send_order_delivered,
    send_order_out_for_delivery,
    send_order_ready,
)


@receiver(post_save, sender=Order)
def send_order_sms_notifications(sender, instance, created, **kwargs):
    """Send SMS notifications on order status changes."""
    sms_settings = SMSSettings.get()
    if not sms_settings.enabled:
        return
    
    # Send confirmation on new order
    if created:
        send_order_confirmation(instance)
        return
    
    # Send ready notification when status changes to ready.
    if instance.status == Order.OrderStatus.READY and not instance.is_delivery:
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_READY
        ).exists()
        
        if not already_sent:
            send_order_ready(instance)
        return

    if instance.status == Order.OrderStatus.OUT_FOR_DELIVERY:
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_OUT_FOR_DELIVERY,
        ).exists()

        if not already_sent:
            send_order_out_for_delivery(instance)
        return

    if instance.status == Order.OrderStatus.COMPLETED and instance.is_delivery:
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_DELIVERED,
        ).exists()

        if not already_sent:
            send_order_delivered(instance)
