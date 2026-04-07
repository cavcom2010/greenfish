"""SMS service using Twilio."""
import logging

from django.conf import settings

from apps.core.models import SiteSettings

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

from .models import SMSMessage, SMSSettings

logger = logging.getLogger(__name__)


def get_twilio_client():
    """Get configured Twilio client."""
    if not TWILIO_AVAILABLE:
        logger.warning("Twilio not installed. Install with: pip install twilio")
        return None
    
    sms_settings = SMSSettings.get()
    if not sms_settings.is_configured:
        logger.warning("SMS not configured properly")
        return None
    
    return Client(
        sms_settings.twilio_account_sid,
        sms_settings.twilio_auth_token
    )


def format_phone_number(phone):
    """Format phone number to E.164 format."""
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone.startswith("0"):
        phone = "+44" + phone[1:]  # Convert UK number
    elif not phone.startswith("+"):
        phone = "+" + phone
    return phone


def send_sms(user, message, message_type, order=None):
    """Send SMS to a user."""
    sms_settings = SMSSettings.get()
    
    # Check if user has phone number
    phone = getattr(user, 'phone_number', None)
    if not phone:
        logger.info(f"No phone number for user {user.email}")
        return None
    
    # Create message record
    sms = SMSMessage.objects.create(
        user=user,
        order=order,
        message_type=message_type,
        phone_number=phone,
        message=message
    )
    
    # Check if SMS is enabled
    if not sms_settings.is_configured:
        logger.info(f"SMS not configured, message saved as pending")
        return sms
    
    # Send via Twilio
    client = get_twilio_client()
    if not client:
        return sms
    
    try:
        formatted_phone = format_phone_number(phone)
        
        twilio_message = client.messages.create(
            body=message,
            from_=sms_settings.twilio_phone_number,
            to=formatted_phone
        )
        
        sms.twilio_sid = twilio_message.sid
        sms.status = SMSMessage.Status.SENT
        sms.save()
        
        logger.info(f"SMS sent to {phone}, SID: {twilio_message.sid}")
        return sms
        
    except Exception as e:
        logger.error(f"Failed to send SMS: {e}")
        sms.status = SMSMessage.Status.FAILED
        sms.error_message = str(e)
        sms.save()
        return sms


def send_sms_to_phone(phone, message, message_type, order=None):
    """Send SMS directly to a phone number (for guest orders)."""
    sms_settings = SMSSettings.get()
    
    if not sms_settings.is_configured:
        logger.info(f"SMS not configured, message not sent")
        return None
    
    # Create message record (no user attached for guest orders)
    sms = SMSMessage.objects.create(
        order=order,
        message_type=message_type,
        phone_number=phone,
        message=message
    )
    
    # Send via Twilio
    client = get_twilio_client()
    if not client:
        return sms
    
    try:
        formatted_phone = format_phone_number(phone)
        
        twilio_message = client.messages.create(
            body=message,
            from_=sms_settings.twilio_phone_number,
            to=formatted_phone
        )
        
        sms.twilio_sid = twilio_message.sid
        sms.status = SMSMessage.Status.SENT
        sms.save()
        
        logger.info(f"SMS sent to {phone}, SID: {twilio_message.sid}")
        return sms
        
    except Exception as e:
        logger.error(f"Failed to send SMS: {e}")
        sms.status = SMSMessage.Status.FAILED
        sms.error_message = str(e)
        sms.save()
        return sms


def send_order_confirmation(order):
    """Send order confirmation SMS with pickup time."""
    from django.conf import settings
    
    sms_settings = SMSSettings.get()
    if not sms_settings.send_order_confirmed:
        return None
    
    # Get phone number from user or order
    phone = None
    name = "there"
    if order.user:
        phone = order.user.phone_number
        name = order.user.first_name or "there"
    if not phone:
        phone = order.customer_phone
        name = order.customer_name.split()[0] if order.customer_name else "there"
    
    if not phone:
        return None
    
    # Build message with pickup time
    pickup_info = ""
    if order.requested_pickup_time:
        pickup_time = order.requested_pickup_time.strftime("%H:%M")
        pickup_info = f" Pickup: {pickup_time}."
    
    shop = SiteSettings.get()
    shop_url = getattr(settings, 'SHOP_URL', '')
    message = (
        f"Hi {name}! Your order #{order.order_number} "
        f"for £{order.total_amount} confirmed.{pickup_info} "
        f"Track: {shop_url}/orders/track/{order.order_number}/"
    )
    
    return send_sms_to_phone(
        phone=phone,
        message=message,
        message_type=SMSMessage.MessageType.ORDER_CONFIRMED,
        order=order
    )


def send_order_ready(order):
    """Send order ready for pickup SMS."""
    sms_settings = SMSSettings.get()
    if not sms_settings.send_order_ready:
        return None
    
    # Get phone number from user or order
    phone = None
    name = ""
    if order.user:
        phone = order.user.phone_number
        name = order.user.first_name or ""
    if not phone:
        phone = order.customer_phone
        name = order.customer_name.split()[0] if order.customer_name else ""
    
    if not phone:
        return None
    
    shop = SiteSettings.get()
    message = (
        f"Great news {name}! Your order #{order.order_number} "
        f"is ready for pickup at {shop.shop_name}. "
        f"Quote: {order.order_number}. See you soon!"
    )
    
    return send_sms_to_phone(
        phone=phone,
        message=message,
        message_type=SMSMessage.MessageType.ORDER_READY,
        order=order
    )


def send_welcome_sms(user):
    """Send welcome SMS to new user."""
    sms_settings = SMSSettings.get()
    
    shop = SiteSettings.get()
    shop_url = getattr(settings, 'SHOP_URL', '')
    message = (
        f"Welcome to {shop.shop_name}, {user.first_name or 'there'}! "
        f"Order delicious food and earn rewards. "
        f"Visit: {shop_url}"
    )
    
    return send_sms(
        user=user,
        message=message,
        message_type=SMSMessage.MessageType.WELCOME
    )
