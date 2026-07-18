"""Celery tasks for the payments app."""
from celery import shared_task

from .services import expire_due_offline_payments


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def expire_unpaid_orders_task():
    """Cancel offline fallback orders that were not paid within the hold window."""
    return expire_due_offline_payments()
