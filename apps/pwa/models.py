"""
PWA models - Push notification subscriptions.
"""
from django.db import models


class PushSubscription(models.Model):
    """
    Store push notification subscriptions for users.
    
    Each user can have multiple subscriptions (different devices).
    """
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
        null=True,
        blank=True
    )
    
    # Subscription data from the browser
    endpoint = models.URLField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    
    # Device info
    device_name = models.CharField(max_length=100, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "pwa_push_subscriptions"
        verbose_name = "Push Subscription"
        verbose_name_plural = "Push Subscriptions"
    
    def __str__(self):
        return f"Push subscription for {self.user or 'Anonymous'}"
