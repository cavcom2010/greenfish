from django.test import TestCase

from apps.core.models import NotificationEvent
from apps.core.notifications import dispatch_due_notifications, enqueue_notification


class NotificationOutboxTests(TestCase):
    def test_dispatch_marks_unsupported_event_failed_without_crashing(self):
        enqueue_notification(
            channel=NotificationEvent.Channel.EMAIL,
            event_type="test",
            recipient="customer@example.com",
            payload={"message": "Hello"},
        )

        self.assertEqual(dispatch_due_notifications(), 1)
        event = NotificationEvent.objects.get()
        self.assertEqual(event.status, NotificationEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertIn("Unsupported notification channel", event.last_error)
