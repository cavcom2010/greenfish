from django.apps import AppConfig


class SMSConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sms"
    verbose_name = "SMS Notifications"
