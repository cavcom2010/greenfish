"""Celery tasks for account privacy housekeeping."""
from celery import shared_task
from django.core.management import call_command


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_customer_data_requests_task():
    """Process pending GDPR export/anonymisation requests."""
    call_command("process_customer_data_requests")


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def anonymise_old_order_personal_data_task():
    """Apply the personal-data retention policy to old orders."""
    call_command("anonymise_old_order_personal_data")
