from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.core.models import NotificationEvent
from apps.core.notifications import dispatch_due_notifications, enqueue_notification


class NotificationOutboxTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_dispatch_sends_email_event(self):
        enqueue_notification(
            channel=NotificationEvent.Channel.EMAIL,
            event_type="order_receipt",
            recipient="customer@example.com",
            payload={
                "subject": "Your GreenFish receipt",
                "message": "Plain receipt",
                "html_body": "<strong>HTML receipt</strong>",
            },
        )

        self.assertEqual(dispatch_due_notifications(), 1)
        event = NotificationEvent.objects.get()
        self.assertEqual(event.status, NotificationEvent.Status.SENT)
        self.assertEqual(event.attempts, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Your GreenFish receipt")
        self.assertEqual(mail.outbox[0].to, ["customer@example.com"])
        self.assertEqual(mail.outbox[0].alternatives[0][0], "<strong>HTML receipt</strong>")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_test_email_management_command(self):
        output = StringIO()

        call_command("send_test_email", "preview@example.com", "--subject", "Preview", stdout=output)

        self.assertIn("Sent 1 test email", output.getvalue())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Preview")

    def test_dispatch_retries_email_failures(self):
        enqueue_notification(
            channel=NotificationEvent.Channel.EMAIL,
            event_type="test",
            recipient="customer@example.com",
            payload={"message": "Hello"},
        )

        with patch("apps.core.notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("smtp down")):
            self.assertEqual(dispatch_due_notifications(), 1)

        event = NotificationEvent.objects.get()
        self.assertEqual(event.status, NotificationEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertIn("smtp down", event.last_error)

    def test_dispatch_marks_unsupported_event_failed_without_crashing(self):
        enqueue_notification(
            channel="fax",
            event_type="test",
            recipient="customer@example.com",
            payload={"message": "Hello"},
        )

        self.assertEqual(dispatch_due_notifications(), 1)
        event = NotificationEvent.objects.get()
        self.assertEqual(event.status, NotificationEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertIn("Unsupported notification channel", event.last_error)
