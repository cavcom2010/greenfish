from celery import shared_task

from .notifications import dispatch_due_notifications


@shared_task
def dispatch_due_notifications_task(limit=50):
    return dispatch_due_notifications(limit=limit)
