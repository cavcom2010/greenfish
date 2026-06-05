from django.core.management.base import BaseCommand, CommandError

from apps.sms.models import SMSMessage
from apps.sms.services import SMS_BACKEND_TWILIO, send_sms_to_phone, sms_backend


class Command(BaseCommand):
    help = "Send or simulate a test SMS through the configured SMS backend."

    def add_arguments(self, parser):
        parser.add_argument("phone", help="Destination phone number, for example +447700900123.")
        parser.add_argument("--message", default="GreenFish test SMS from the configured SMS backend.")
        parser.add_argument(
            "--live",
            action="store_true",
            help="Required when SMS_BACKEND=twilio because this sends a real paid SMS.",
        )

    def handle(self, *args, **options):
        backend = sms_backend()
        if backend == SMS_BACKEND_TWILIO and not options["live"]:
            raise CommandError("SMS_BACKEND=twilio sends real texts. Re-run with --live to confirm.")

        sms = send_sms_to_phone(
            phone=options["phone"],
            message=options["message"],
            message_type=SMSMessage.MessageType.REMINDER,
        )
        if sms.status == SMSMessage.Status.FAILED:
            raise CommandError(f"Test SMS failed: {sms.error_message}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Test SMS {sms.status} via {backend}: id={sms.id}, sid={sms.twilio_sid or '-'}."
            )
        )
