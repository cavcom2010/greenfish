from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from apps.core.models import NotificationEvent
from apps.core.notifications import dispatch_due_notifications, enqueue_notification
from apps.core.test_support import create_order, ensure_site_settings
from apps.sms.models import SMSMessage, SMSSettings
from apps.sms.services import send_sms_to_phone


class SMSBackendTests(TestCase):
    def setUp(self):
        ensure_site_settings()

    @override_settings(SMS_BACKEND="console")
    def test_console_backend_records_sent_sms_without_twilio(self):
        with patch("apps.sms.services.get_twilio_client") as get_client:
            sms = send_sms_to_phone("+447700900123", "Console test", SMSMessage.MessageType.REMINDER)

        get_client.assert_not_called()
        self.assertEqual(sms.status, SMSMessage.Status.SENT)
        self.assertEqual(sms.twilio_sid, "console")
        self.assertEqual(sms.phone_number, "+447700900123")

    @override_settings(
        SMS_BACKEND="twilio_test",
        TWILIO_TEST_ACCOUNT_SID="AC_test",
        TWILIO_TEST_AUTH_TOKEN="test-token",
        TWILIO_TEST_PHONE_NUMBER="+15005550006",
    )
    @patch("apps.sms.services.TWILIO_AVAILABLE", True)
    @patch("apps.sms.services.Client")
    def test_twilio_test_backend_uses_magic_sender(self, client_class):
        twilio_message = Mock(sid="SM_TEST")
        client = client_class.return_value
        client.messages.create.return_value = twilio_message

        sms = send_sms_to_phone("07700 900123", "Provider test", SMSMessage.MessageType.REMINDER)

        self.assertEqual(sms.status, SMSMessage.Status.SENT)
        self.assertEqual(sms.twilio_sid, "SM_TEST")
        client_class.assert_called_once_with("AC_test", "test-token")
        client.messages.create.assert_called_once_with(
            body="Provider test",
            from_="+15005550006",
            to="+447700900123",
        )

    @override_settings(
        SMS_BACKEND="twilio",
        TWILIO_ACCOUNT_SID="AC_live",
        TWILIO_AUTH_TOKEN="live-token",
        TWILIO_PHONE_NUMBER="+441234567890",
    )
    @patch("apps.sms.services.TWILIO_AVAILABLE", True)
    @patch("apps.sms.services.Client")
    def test_twilio_failure_marks_sms_failed(self, client_class):
        client = client_class.return_value
        client.messages.create.side_effect = RuntimeError("twilio down")

        sms = send_sms_to_phone("+447700900123", "Live test", SMSMessage.MessageType.REMINDER)

        self.assertEqual(sms.status, SMSMessage.Status.FAILED)
        self.assertIn("twilio down", sms.error_message)

    @override_settings(SMS_BACKEND="twilio")
    def test_send_test_sms_blocks_live_backend_without_live_flag(self):
        with patch("apps.sms.management.commands.send_test_sms.send_sms_to_phone") as send_sms:
            with self.assertRaisesMessage(CommandError, "Re-run with --live"):
                call_command("send_test_sms", "+447700900123")

        send_sms.assert_not_called()

    @override_settings(SMS_BACKEND="console")
    def test_send_test_sms_management_command_console_backend(self):
        output = StringIO()

        call_command("send_test_sms", "+447700900123", stdout=output)

        self.assertIn("Test SMS sent via console", output.getvalue())
        self.assertEqual(SMSMessage.objects.count(), 1)

    @override_settings(SMS_BACKEND="console")
    def test_sms_notification_event_dispatches_to_selected_backend(self):
        enqueue_notification(
            channel=NotificationEvent.Channel.SMS,
            event_type=SMSMessage.MessageType.ORDER_CONFIRMED,
            recipient="+447700900123",
            payload={"message_type": SMSMessage.MessageType.ORDER_CONFIRMED, "message": "Order confirmed"},
        )

        self.assertEqual(dispatch_due_notifications(), 1)

        event = NotificationEvent.objects.get()
        sms = SMSMessage.objects.get()
        self.assertEqual(event.status, NotificationEvent.Status.SENT)
        self.assertEqual(sms.status, SMSMessage.Status.SENT)
        self.assertEqual(sms.twilio_sid, "console")

    @override_settings(SMS_BACKEND="console")
    def test_order_signal_enqueues_sms_and_dispatches_when_enabled(self):
        sms_settings = SMSSettings.get()
        sms_settings.enabled = True
        sms_settings.save()

        order = create_order(customer_phone="+447700900123")

        event = NotificationEvent.objects.get(channel=NotificationEvent.Channel.SMS, order=order)
        self.assertEqual(event.status, NotificationEvent.Status.PENDING)

        self.assertEqual(dispatch_due_notifications(), 1)
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.SENT)
        self.assertTrue(SMSMessage.objects.filter(order=order, status=SMSMessage.Status.SENT).exists())
