"""SMS signals for automatic notifications."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order

from .services import send_order_confirmation, send_order_ready
from .models import SMSSettings


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
    
    # Send ready notification when status changes to ready
    if instance.status == Order.Status.READY:
        # Check if we already sent this notification
        from .models import SMSMessage
        already_sent = SMSMessage.objects.filter(
            order=instance,
            message_type=SMSMessage.MessageType.ORDER_READY
        ).exists()
        
        if not already_sent:
            send_order_ready(instance)
