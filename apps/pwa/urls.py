"""
URL patterns for the PWA app.
"""
from django.urls import path

from . import views

app_name = "pwa"

urlpatterns = [
    path("manifest.json", views.manifest, name="manifest"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
    
    # Push notification endpoints
    path("push/subscribe/", views.subscribe_push, name="subscribe_push"),
    path("push/unsubscribe/", views.unsubscribe_push, name="unsubscribe_push"),
    path("push/status/", views.push_status, name="push_status"),
]
