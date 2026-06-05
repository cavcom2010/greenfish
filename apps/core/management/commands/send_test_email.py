from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email through the configured Django email backend."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Email address that should receive the test message.")
        parser.add_argument("--subject", default="GreenFish test email")
        parser.add_argument(
            "--message",
            default="This is a GreenFish test email from the configured Django email backend.",
        )
        parser.add_argument("--html", default="", help="Optional HTML body for preview testing.")

    def handle(self, *args, **options):
        recipient = options["recipient"].strip()
        if not recipient:
            raise CommandError("Recipient email is required.")

        email = EmailMultiAlternatives(
            subject=options["subject"],
            body=options["message"],
            to=[recipient],
        )
        if options["html"]:
            email.attach_alternative(options["html"], "text/html")
        sent_count = email.send(fail_silently=False)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent_count} test email(s) to {recipient}."))
