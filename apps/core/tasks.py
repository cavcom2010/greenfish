from celery import shared_task
from django.core.management import call_command

from .notifications import dispatch_due_notifications


@shared_task
def dispatch_due_notifications_task(limit=50):
    return dispatch_due_notifications(limit=limit)


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def clear_expired_sessions_task():
    """Purge expired database-backed sessions."""
    call_command("clearsessions")
