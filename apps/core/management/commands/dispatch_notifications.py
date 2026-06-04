from django.core.management.base import BaseCommand

from apps.core.notifications import dispatch_due_notifications


class Command(BaseCommand):
    help = "Dispatch due notification outbox events."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        count = dispatch_due_notifications(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Dispatched {count} notification event(s)."))
