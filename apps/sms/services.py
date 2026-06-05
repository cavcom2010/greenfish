"""SMS service with console, Twilio test, and Twilio live backends."""
import logging

from django.conf import settings
from django.utils import timezone

from apps.core.models import SiteSettings

try:
    from twilio.rest import Client

    TWILIO_AVAILABLE = True
except ImportError:
    Client = None
    TWILIO_AVAILABLE = False

from .models import SMSMessage, SMSSettings

logger = logging.getLogger(__name__)

SMS_BACKEND_CONSOLE = "console"
SMS_BACKEND_TWILIO_TEST = "twilio_test"
SMS_BACKEND_TWILIO = "twilio"
SMS_BACKENDS = {SMS_BACKEND_CONSOLE, SMS_BACKEND_TWILIO_TEST, SMS_BACKEND_TWILIO}


class SMSConfigurationError(RuntimeError):
    """Raised when the selected SMS backend cannot send."""


def sms_backend():
    """Return the configured SMS backend name."""
    backend = str(getattr(settings, "SMS_BACKEND", SMS_BACKEND_CONSOLE) or SMS_BACKEND_CONSOLE).strip().lower()
    if backend not in SMS_BACKENDS:
        raise SMSConfigurationError(f"Unsupported SMS_BACKEND: {backend}")
    return backend


def format_phone_number(phone):
    """Format phone number to E.164 format."""
    phone = (phone or "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone.startswith("0"):
        phone = "+44" + phone[1:]
    elif phone and not phone.startswith("+"):
        phone = "+" + phone
    return phone


def _setting_or_sms_setting(name, sms_settings, field_name, default=""):
    value = getattr(settings, name, default)
    return value or getattr(sms_settings, field_name, default)


def sms_provider_config():
    """Return provider config from env first, then SMSSettings fallback."""
    backend = sms_backend()
    sms_settings = SMSSettings.get()
    if backend == SMS_BACKEND_CONSOLE:
        return {
            "backend": backend,
            "account_sid": "",
            "auth_token": "",
            "from_number": "console",
            "settings": sms_settings,
        }
    if backend == SMS_BACKEND_TWILIO_TEST:
        return {
            "backend": backend,
            "account_sid": (
                getattr(settings, "TWILIO_TEST_ACCOUNT_SID", "")
                or getattr(settings, "TWILIO_ACCOUNT_SID", "")
                or sms_settings.twilio_account_sid
            ),
            "auth_token": (
                getattr(settings, "TWILIO_TEST_AUTH_TOKEN", "")
                or getattr(settings, "TWILIO_AUTH_TOKEN", "")
                or sms_settings.twilio_auth_token
            ),
            "from_number": getattr(settings, "TWILIO_TEST_PHONE_NUMBER", "+15005550006") or "+15005550006",
            "settings": sms_settings,
        }
    return {
        "backend": backend,
        "account_sid": _setting_or_sms_setting("TWILIO_ACCOUNT_SID", sms_settings, "twilio_account_sid"),
        "auth_token": _setting_or_sms_setting("TWILIO_AUTH_TOKEN", sms_settings, "twilio_auth_token"),
        "from_number": _setting_or_sms_setting("TWILIO_PHONE_NUMBER", sms_settings, "twilio_phone_number"),
        "settings": sms_settings,
    }


def get_twilio_client(config=None):
    """Get a configured Twilio client for test/live backends."""
    config = config or sms_provider_config()
    if config["backend"] == SMS_BACKEND_CONSOLE:
        return None
    if not TWILIO_AVAILABLE:
        raise SMSConfigurationError("Twilio is not installed. Install requirements.txt.")
    if not (config["account_sid"] and config["auth_token"] and config["from_number"]):
        raise SMSConfigurationError(f"{config['backend']} SMS credentials are incomplete.")
    return Client(config["account_sid"], config["auth_token"])


def _create_sms_record(*, phone, message, message_type, order=None, user=None):
    return SMSMessage.objects.create(
        user=user,
        order=order,
        message_type=message_type,
        phone_number=phone,
        message=message,
    )


def _mark_sms_failed(sms, error):
    sms.status = SMSMessage.Status.FAILED
    sms.error_message = str(error)
    sms.save(update_fields=["status", "error_message", "updated_at"])
    logger.error("Failed to send SMS: %s", error)
    return sms


def _dispatch_sms_record(sms):
    config = sms_provider_config()
    try:
        sms_settings = config["settings"]
        sent_today = SMSMessage.objects.filter(
            created_at__date=timezone.localdate(),
            status__in=[SMSMessage.Status.SENT, SMSMessage.Status.DELIVERED],
        ).count()
        if sent_today >= sms_settings.max_daily_messages:
            return _mark_sms_failed(sms, "Daily SMS limit reached.")

        if config["backend"] == SMS_BACKEND_CONSOLE:
            sms.twilio_sid = "console"
            sms.status = SMSMessage.Status.SENT
            sms.save(update_fields=["twilio_sid", "status", "updated_at"])
            logger.info("Console SMS to %s: %s", sms.phone_number, sms.message)
            return sms

        client = get_twilio_client(config)
        twilio_message = client.messages.create(
            body=sms.message,
            from_=config["from_number"],
            to=format_phone_number(sms.phone_number),
        )
        sms.twilio_sid = twilio_message.sid
        sms.status = SMSMessage.Status.SENT
        sms.save(update_fields=["twilio_sid", "status", "updated_at"])
        logger.info("SMS sent to %s via %s, SID: %s", sms.phone_number, config["backend"], twilio_message.sid)
        return sms
    except Exception as exc:
        return _mark_sms_failed(sms, exc)


def send_sms(user, message, message_type, order=None):
    """Send SMS to a user."""
    phone = getattr(user, "phone_number", None)
    if not phone:
        logger.info("No phone number for user %s", getattr(user, "email", ""))
        return None
    sms = _create_sms_record(user=user, order=order, message_type=message_type, phone=phone, message=message)
    return _dispatch_sms_record(sms)


def send_sms_to_phone(phone, message, message_type, order=None):
    """Send SMS directly to a phone number, preserving an SMSMessage audit row."""
    sms = _create_sms_record(order=order, message_type=message_type, phone=phone, message=message)
    return _dispatch_sms_record(sms)


def send_order_confirmation(order):
    """Send order confirmation SMS with fulfilment timing."""
    sms_settings = SMSSettings.get()
    if not sms_settings.send_order_confirmed:
        return None

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

    service_info = ""
    if order.requested_service_time:
        service_time = order.requested_service_time.strftime("%H:%M")
        if order.is_delivery:
            service_info = f" Delivery target: {service_time}."
        else:
            service_info = f" Pickup: {service_time}."

    shop_url = getattr(settings, "SHOP_URL", "")
    message = (
        f"Hi {name}! Your order #{order.order_number} "
        f"for £{order.total_amount} confirmed.{service_info} "
        f"Track: {shop_url}/orders/track/{order.order_number}/"
    )

    return send_sms_to_phone(
        phone=phone,
        message=message,
        message_type=SMSMessage.MessageType.ORDER_CONFIRMED,
        order=order,
    )


def send_order_ready(order):
    """Send order ready SMS."""
    sms_settings = SMSSettings.get()
    if not sms_settings.send_order_ready:
        return None

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
        order=order,
    )


def send_order_out_for_delivery(order):
    """Send order dispatch SMS."""
    sms_settings = SMSSettings.get()
    if not sms_settings.send_order_ready:
        return None

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
        f"is on the way from {shop.shop_name}. "
        f"Track it here: {getattr(settings, 'SHOP_URL', '')}/orders/track/{order.order_number}/"
    )

    return send_sms_to_phone(
        phone=phone,
        message=message,
        message_type=SMSMessage.MessageType.ORDER_OUT_FOR_DELIVERY,
        order=order,
    )


def send_order_delivered(order):
    """Send optional delivery-complete SMS."""
    sms_settings = SMSSettings.get()
    if not sms_settings.send_order_delivered:
        return None

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
        f"Thanks {name}! Your order #{order.order_number} "
        f"from {shop.shop_name} has been delivered. Enjoy your meal."
    )

    return send_sms_to_phone(
        phone=phone,
        message=message,
        message_type=SMSMessage.MessageType.ORDER_DELIVERED,
        order=order,
    )


def send_welcome_sms(user):
    """Send welcome SMS to new user."""
    shop = SiteSettings.get()
    shop_url = getattr(settings, "SHOP_URL", "")
    message = (
        f"Welcome to {shop.shop_name}, {user.first_name or 'there'}! "
        f"Order delicious food and earn rewards. "
        f"Visit: {shop_url}"
    )

    return send_sms(
        user=user,
        message=message,
        message_type=SMSMessage.MessageType.WELCOME,
    )
