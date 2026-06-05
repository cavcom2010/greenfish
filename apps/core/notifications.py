import logging

from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .models import NotificationEvent

logger = logging.getLogger(__name__)


def enqueue_notification(*, channel, event_type, recipient="", payload=None, order=None):
    """Create a durable notification event for asynchronous delivery."""
    return NotificationEvent.objects.create(
        channel=channel,
        event_type=event_type,
        recipient=recipient or "",
        payload=payload or {},
        order=order,
        next_attempt_at=timezone.now(),
    )


def dispatch_notification_event(event):
    """Send one notification event and update retry state."""
    if event.status not in {NotificationEvent.Status.PENDING, NotificationEvent.Status.FAILED}:
        return event

    event.attempts += 1
    try:
        if event.channel == NotificationEvent.Channel.SMS:
            from apps.sms.services import send_sms_to_phone
            from apps.sms.models import SMSMessage

            message = event.payload.get("message", "")
            message_type = event.payload.get("message_type", event.event_type)
            sms = send_sms_to_phone(event.recipient, message, message_type, order=event.order)
            if sms and sms.status == SMSMessage.Status.FAILED:
                raise RuntimeError(sms.error_message or "SMS delivery failed")
        elif event.channel == NotificationEvent.Channel.PUSH:
            from apps.pwa.services import notify_order_status

            notify_order_status(event.order, event.payload.get("message", event.event_type))
        elif event.channel == NotificationEvent.Channel.EMAIL:
            subject = event.payload.get("subject") or event.event_type.replace("_", " ").title()
            text_body = event.payload.get("text_body") or event.payload.get("message") or ""
            html_body = event.payload.get("html_body") or event.payload.get("html_message") or ""
            email = EmailMultiAlternatives(subject=subject, body=text_body, to=[event.recipient])
            if html_body:
                email.attach_alternative(html_body, "text/html")
            email.send(fail_silently=False)
        else:
            raise ValueError(f"Unsupported notification channel: {event.channel}")
    except Exception as exc:
        logger.exception("Notification event %s failed", event.pk)
        event.last_error = str(exc)
        if event.attempts >= event.max_attempts:
            event.status = NotificationEvent.Status.FAILED
            event.next_attempt_at = None
        else:
            event.status = NotificationEvent.Status.PENDING
            event.next_attempt_at = timezone.now() + timezone.timedelta(minutes=2 * event.attempts)
    else:
        event.status = NotificationEvent.Status.SENT
        event.sent_at = timezone.now()
        event.last_error = ""
        event.next_attempt_at = None

    event.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "sent_at", "updated_at"])
    return event


def dispatch_due_notifications(limit=50):
    now = timezone.now()
    events = NotificationEvent.objects.filter(
        status=NotificationEvent.Status.PENDING,
        next_attempt_at__lte=now,
    ).select_related("order")[:limit]
    count = 0
    for event in events:
        dispatch_notification_event(event)
        count += 1
    return count
