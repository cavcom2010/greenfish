"""
Customer signals - Auto-create profiles and handle customer events.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomerProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_customer_profile(sender, instance, created, **kwargs):
    """Automatically create a CustomerProfile when a User is created."""
    if created:
        CustomerProfile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_customer_profile(sender, instance, **kwargs):
    """Save the CustomerProfile when User is saved."""
    if hasattr(instance, 'profile'):
        instance.profile.save()
