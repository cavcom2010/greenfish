"""
Payment models for Tinashe Takeaway.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Payment(models.Model):
    """Payment record for an order."""

    class Provider(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        MOLLIE = "mollie", "Mollie"
        DEMO = "demo", "Demo"
        OFFLINE_PENDING = "offline_pending", "Offline Pending"
    
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

    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.STRIPE,
        db_index=True,
    )

    external_payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    external_payment_method = models.CharField(max_length=50, blank=True)
    
    # Legacy Mollie fields kept for backwards compatibility and future re-enablement.
    mollie_payment_id = models.CharField(max_length=100, blank=True, db_index=True)
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
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"Payment {self.payment_reference} - {self.status}"

    @property
    def payment_reference(self):
        return self.external_payment_id or self.mollie_payment_id or f"payment-{self.pk}"

    @property
    def payment_method_label(self):
        return self.external_payment_method or self.mollie_payment_method

    @property
    def is_demo(self):
        return self.provider == self.Provider.DEMO or self.payment_reference.startswith("demo_")

    @property
    def is_offline_pending(self):
        return self.provider == self.Provider.OFFLINE_PENDING

    def save(self, *args, **kwargs):
        if not self.external_payment_id and self.mollie_payment_id:
            self.external_payment_id = self.mollie_payment_id
        if not self.external_payment_method and self.mollie_payment_method:
            self.external_payment_method = self.mollie_payment_method

        if self.provider == self.Provider.MOLLIE:
            if self.external_payment_id and not self.mollie_payment_id:
                self.mollie_payment_id = self.external_payment_id
            if self.external_payment_method and not self.mollie_payment_method:
                self.mollie_payment_method = self.external_payment_method

        super().save(*args, **kwargs)


class ManualPaymentReceipt(models.Model):
    """Immutable evidence for a manually recorded in-shop/phone payment."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD_TERMINAL = "card_terminal", "Card Terminal"
        PHONE_CARD = "phone_card", "Phone Card"

    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="manual_receipt",
    )
    method = models.CharField(max_length=20, choices=Method.choices, db_index=True)
    amount_due = models.DecimalField(max_digits=8, decimal_places=2)
    amount_received = models.DecimalField(max_digits=8, decimal_places=2)
    change_given = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    reference_code = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manual_payment_receipts",
    )
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Manual Payment Receipt"
        verbose_name_plural = "Manual Payment Receipts"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.payment.payment_reference} - {self.get_method_display()} - £{self.amount_received}"

    def save(self, *args, **kwargs):
        if self.pk and ManualPaymentReceipt.objects.filter(pk=self.pk).exists():
            raise ValidationError("Manual payment receipts are immutable.")
        super().save(*args, **kwargs)


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
        return f"{self.payment.payment_reference} - {self.event_type}"


class PaymentWebhookEvent(models.Model):
    """Idempotency record for provider webhook events."""

    provider = models.CharField(max_length=20, choices=Payment.Provider.choices, db_index=True)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100, blank=True)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_events",
    )
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("provider", "event_id")]
        indexes = [models.Index(fields=["provider", "event_type", "created_at"])]

    def __str__(self):
        return f"{self.provider}:{self.event_id}"


class RefundRequest(models.Model):
    """Staff initiated refund workflow."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refund_requests")
    amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refund_requests",
    )
    provider_reference = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["status", "requested_at"])]

    def __str__(self):
        return f"Refund {self.payment.payment_reference} ({self.status})"
