"""Expire unpaid offline fallback orders whose hold window has elapsed."""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.services import expire_offline_pending_payment


class Command(BaseCommand):
    help = "Cancel offline pending orders that were not paid within the configured hold window."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show how many orders would expire without changing them.")

    def handle(self, *args, **options):
        now = timezone.now()
        queryset = Payment.objects.select_related("order").filter(
            provider=Payment.Provider.OFFLINE_PENDING,
            status=Payment.Status.PENDING,
            expires_at__isnull=False,
            expires_at__lte=now,
            order__payment_status__in=["pending"],
        )
        count = queryset.count()
        if options["dry_run"]:
            self.stdout.write(f"{count} unpaid fallback order(s) would be expired.")
            return

        hold_minutes = getattr(settings, "PAYMENT_FALLBACK_HOLD_MINUTES", 15)
        reason = f"Payment not received within {hold_minutes} minutes. Order automatically cancelled."
        for payment in queryset:
            expire_offline_pending_payment(payment, reason=reason)

        self.stdout.write(self.style.SUCCESS(f"Expired {count} unpaid fallback order(s)."))
