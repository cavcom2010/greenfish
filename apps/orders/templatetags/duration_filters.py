"""Template filters for duration/time calculations."""
from datetime import timedelta

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def is_urgent(created_at, minutes=15):
    """Check if order is urgent (older than specified minutes)."""
    if not created_at:
        return False
    
    age = timezone.now() - created_at
    return age > timedelta(minutes=minutes)


@register.filter
def order_age_minutes(created_at):
    """Return order age in minutes."""
    if not created_at:
        return 0
    
    age = timezone.now() - created_at
    return int(age.total_seconds() / 60)
