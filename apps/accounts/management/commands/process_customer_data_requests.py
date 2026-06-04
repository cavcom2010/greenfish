from django.core.management.base import BaseCommand

from apps.accounts.models import CustomerDataRequest
from apps.accounts.privacy import process_customer_data_request


class Command(BaseCommand):
    help = "Process pending customer data export/anonymisation requests."

    def handle(self, *args, **options):
        queryset = CustomerDataRequest.objects.filter(status=CustomerDataRequest.Status.REQUESTED)
        count = 0
        for data_request in queryset:
            process_customer_data_request(data_request)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Processed {count} customer data request(s)."))
