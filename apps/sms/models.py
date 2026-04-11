"""
SMS notification models for Tinashe Takeaway.
"""
from django.db import models


class SMSMessage(models.Model):
    """Record of all SMS messages sent."""
    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
    
    class MessageType(models.TextChoices):
        ORDER_CONFIRMED = "order_confirmed", "Order Confirmed"
        ORDER_READY = "order_ready", "Order Ready"
        ORDER_OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
        ORDER_DELIVERED = "delivered", "Order Delivered"
        PROMO = "promo", "Promotional"
        WELCOME = "welcome", "Welcome"
        REMINDER = "reminder", "Reminder"
    
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="sms_messages",
        null=True,
        blank=True,
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_messages"
    )
    
    message_type = models.CharField(max_length=30, choices=MessageType.choices)
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    
    # Twilio tracking
    twilio_sid = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SMS Message"
        verbose_name_plural = "SMS Messages"
    
    def __str__(self):
        return f"SMS to {self.phone_number} ({self.message_type})"


class SMSSettings(models.Model):
    """SMS configuration settings."""
    
    # Twilio credentials
    twilio_account_sid = models.CharField(max_length=100, blank=True)
    twilio_auth_token = models.CharField(max_length=100, blank=True)
    twilio_phone_number = models.CharField(max_length=20, blank=True, help_text="Twilio phone number to send from")
    
    # Enable/disable features
    enabled = models.BooleanField(default=False)
    send_order_confirmed = models.BooleanField(default=True)
    send_order_ready = models.BooleanField(default=True)
    send_order_delivered = models.BooleanField(default=False)
    send_promotions = models.BooleanField(default=False)
    
    # Rate limiting
    max_daily_messages = models.PositiveIntegerField(default=100)
    
    class Meta:
        verbose_name = "SMS Settings"
        verbose_name_plural = "SMS Settings"
    
    def __str__(self):
        return "SMS Settings"
    
    @classmethod
    def get(cls):
        """Get or create singleton settings."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings
    
    @property
    def is_configured(self):
        return all([
            self.enabled,
            self.twilio_account_sid,
            self.twilio_auth_token,
            self.twilio_phone_number
        ])
