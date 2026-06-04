import os

# Set default settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

from .celery import app as celery_app

__all__ = ("celery_app",)
