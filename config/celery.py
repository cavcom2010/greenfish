import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("greenfish")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

#: Periodic housekeeping. Run the worker with beat enabled
#: (`celery -A config worker -B`) or a dedicated `celery -A config beat`
#: process — see deploy/production/systemd/.
app.conf.beat_schedule = {
    "dispatch-due-notifications": {
        "task": "apps.core.tasks.dispatch_due_notifications_task",
        "schedule": 60.0,
    },
    "expire-unpaid-orders": {
        "task": "apps.payments.tasks.expire_unpaid_orders_task",
        "schedule": 300.0,
    },
    "process-customer-data-requests": {
        "task": "apps.accounts.tasks.process_customer_data_requests_task",
        "schedule": 900.0,
    },
    "clear-expired-sessions": {
        "task": "apps.core.tasks.clear_expired_sessions_task",
        "schedule": crontab(hour=4, minute=15),
    },
    "anonymise-old-order-personal-data": {
        "task": "apps.accounts.tasks.anonymise_old_order_personal_data_task",
        "schedule": crontab(day_of_week="mon", hour=3, minute=30),
    },
}
