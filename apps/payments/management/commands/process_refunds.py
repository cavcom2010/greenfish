from django.core.management.base import BaseCommand

from apps.payments.models import RefundRequest
from apps.payments.services import process_refund_request


class Command(BaseCommand):
    help = "Process requested payment refunds."

    def handle(self, *args, **options):
        queryset = RefundRequest.objects.filter(status=RefundRequest.Status.REQUESTED)
        count = 0
        for refund in queryset:
            process_refund_request(refund)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Processed {count} refund request(s)."))
