"""Expire unpaid offline fallback orders whose hold window has elapsed."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.services import expire_due_offline_payments


class Command(BaseCommand):
    help = "Cancel offline pending orders that were not paid within the configured hold window."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show how many orders would expire without changing them.")

    def handle(self, *args, **options):
        now = timezone.now()
        if options["dry_run"]:
            count = Payment.objects.filter(
                provider=Payment.Provider.OFFLINE_PENDING,
                status=Payment.Status.PENDING,
                expires_at__isnull=False,
                expires_at__lte=now,
                order__payment_status__in=["pending"],
            ).count()
            self.stdout.write(f"{count} unpaid fallback order(s) would be expired.")
            return

        expired = expire_due_offline_payments(now=now)
        self.stdout.write(self.style.SUCCESS(f"Expired {expired} unpaid fallback order(s)."))
