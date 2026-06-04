import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from .celery import app as celery_app

__all__ = ("celery_app",)
