from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.privacy import anonymise_order_personal_data
from apps.core.models import SiteSettings
from apps.orders.models import Order


class Command(BaseCommand):
    help = "Anonymise customer-identifying data on old orders. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply anonymisation. Without this flag, only report the number of matching orders.",
        )
        parser.add_argument(
            "--years",
            type=int,
            help="Override the SiteSettings retention window in years.",
        )

    def handle(self, *args, **options):
        settings = SiteSettings.get()
        retention_years = options["years"] or settings.order_personal_data_retention_years
        cutoff = timezone.now() - timezone.timedelta(days=retention_years * 365)
        queryset = Order.objects.filter(
            created_at__lt=cutoff,
            personal_data_anonymised_at__isnull=True,
        )
        count = queryset.count()

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {count} order(s) older than {retention_years} year(s) would be anonymised."
                )
            )
            return

        updated = anonymise_order_personal_data(queryset)
        self.stdout.write(
            self.style.SUCCESS(
                f"Anonymised {updated} order(s) older than {retention_years} year(s)."
            )
        )
