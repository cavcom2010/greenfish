"""
Order models for Tinashe Takeaway.
"""
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.menu.models import MenuItem


class Order(models.Model):
    """Customer food order."""
    
    class OrderStatus(models.TextChoices):
        PENDING = "pending", "Pending Payment"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready for Collection"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
    
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
    
    # Order identification
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    
    # Customer information
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=30)
    customer_email = models.EmailField(blank=True)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )
    
    # Order status
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING
    )
    
    # Financial
    subtotal = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00")
    )
    total_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00")
    )
    
    # Applied offer/voucher
    applied_offer = models.ForeignKey(
        "offers.Offer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )
    voucher_code = models.CharField(max_length=20, blank=True)
    
    # Pickup details
    requested_pickup_time = models.DateTimeField(null=True, blank=True, help_text="Customer's requested pickup time")
    estimated_ready_time = models.DateTimeField(null=True, blank=True, help_text="Kitchen's estimated ready time")
    actual_ready_time = models.DateTimeField(null=True, blank=True, help_text="When order was actually marked ready")
    special_instructions = models.TextField(blank=True)
    staff_notes = models.TextField(blank=True, help_text="Internal kitchen notes")
    
    # Payment (Mollie)
    mollie_payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["payment_status", "created_at"]),
        ]
    
    def __str__(self):
        return f"#{self.order_number} - {self.customer_name}"
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        """Generate unique order number."""
        from django.conf import settings
        prefix = getattr(settings, "ORDER_PREFIX", "TN")
        # Use UUID for uniqueness, take first 8 chars
        unique_id = str(uuid.uuid4().int)[:6]
        return f"{prefix}-{unique_id}"
    
    def calculate_totals(self):
        """Calculate order totals from items."""
        subtotal = sum(item.line_total for item in self.items.all())
        self.subtotal = subtotal
        self.total_amount = max(Decimal("0.00"), subtotal - self.discount_amount)
        self.save(update_fields=["subtotal", "total_amount", "updated_at"])
    
    def mark_as_paid(self):
        """Mark order as paid."""
        self.payment_status = self.PaymentStatus.PAID
        self.paid_at = timezone.now()
        # Auto-confirm if pending
        if self.status == self.OrderStatus.PENDING:
            self.status = self.OrderStatus.CONFIRMED
        self.save(update_fields=["payment_status", "paid_at", "status", "updated_at"])
    
    def update_status(self, new_status, changed_by=None):
        """Update order status and log the change."""
        old_status = self.status
        self.status = new_status
        
        # Set estimated ready time when confirmed
        if new_status == self.OrderStatus.CONFIRMED and not self.estimated_ready_time:
            max_prep_time = max(
                (item.menu_item.preparation_time for item in self.items.all() if item.menu_item),
                default=15
            )
            self.estimated_ready_time = timezone.now() + timezone.timedelta(minutes=max_prep_time)
        
        # Set actual ready time
        if new_status == self.OrderStatus.READY and not self.actual_ready_time:
            self.actual_ready_time = timezone.now()
        
        self.save(update_fields=["status", "estimated_ready_time", "actual_ready_time", "updated_at"])
        
        # Log status change
        OrderStatusHistory.objects.create(
            order=self,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by
        )
    
    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())
    
    @property
    def is_urgent(self):
        """Check if order is urgent (over 15 minutes old)."""
        if not self.created_at:
            return False
        elapsed = (timezone.now() - self.created_at).total_seconds() / 60
        return elapsed > 15
    
    @property
    def minutes_elapsed(self):
        """Return minutes since order was created."""
        if not self.created_at:
            return 0
        return int((timezone.now() - self.created_at).total_seconds() / 60)


class OrderItem(models.Model):
    """Individual line item within an order."""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items"
    )
    
    # Snapshot of item details at time of order
    item_name = models.CharField(max_length=150)
    item_price = models.DecimalField(max_digits=6, decimal_places=2)
    
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )
    
    # Modifiers stored as JSON
    modifiers = models.JSONField(
        default=list,
        blank=True,
        help_text='e.g., [{"name": "Extra cheese", "price": 0.50}]'
    )
    
    special_instructions = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
    
    def __str__(self):
        return f"{self.quantity}x {self.item_name}"
    
    @property
    def modifiers_total(self):
        """Calculate total price of modifiers."""
        total = Decimal("0.00")
        for mod in self.modifiers:
            try:
                total += Decimal(str(mod.get("price", 0)))
            except (ValueError, TypeError):
                pass
        return total * self.quantity
    
    @property
    def line_total(self):
        """Total price for this line item including modifiers."""
        base = (self.item_price * self.quantity) + self.modifiers_total
        return base.quantize(Decimal("0.01"))
    
    def save(self, *args, **kwargs):
        # Snapshot item details if not set
        if not self.item_name and self.menu_item:
            self.item_name = self.menu_item.name
            self.item_price = self.menu_item.price
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    """History of order status changes."""
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history"
    )
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Order Status History"
        verbose_name_plural = "Order Status Histories"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.order.order_number}: {self.old_status} → {self.new_status}"
