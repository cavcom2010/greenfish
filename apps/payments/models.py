"""
Payment models for Tinashe Takeaway.
"""
from django.db import models


class Payment(models.Model):
    """Payment record for an order."""
    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
    
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment"
    )
    
    # Mollie payment details
    mollie_payment_id = models.CharField(max_length=100, db_index=True)
    mollie_payment_method = models.CharField(max_length=50, blank=True)
    
    # Amount
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default="GBP")
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # URLs
    checkout_url = models.URLField(blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Payment {self.mollie_payment_id} - {self.status}"


class PaymentLog(models.Model):
    """Log of payment events for debugging."""
    
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="logs"
    )
    event_type = models.CharField(max_length=50)
    event_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Payment Log"
        verbose_name_plural = "Payment Logs"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.payment.mollie_payment_id} - {self.event_type}"
