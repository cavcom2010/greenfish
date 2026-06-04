"""
Order models for Tinashe Takeaway.
"""
import uuid
from decimal import Decimal
from secrets import token_urlsafe

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.menu.models import MenuItem


def default_preparation_time_minutes():
    """Return the safe default prep time used when an item snapshot is missing."""
    try:
        return max(1, int(getattr(settings, "DEFAULT_PREP_TIME", 15)))
    except (TypeError, ValueError):
        return 15


def generate_public_access_token():
    return token_urlsafe(24)


class Order(models.Model):
    """Customer food order."""

    class ServiceType(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        DELIVERY = "delivery", "Delivery"
    
    class OrderStatus(models.TextChoices):
        PENDING = "pending", "Pending Payment"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready for Collection"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
    
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
    
    # Order identification
    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    public_access_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_public_access_token,
        editable=False,
    )
    
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

    service_type = models.CharField(
        max_length=20,
        choices=ServiceType.choices,
        default=ServiceType.PICKUP,
        db_index=True,
    )
    delivery_address_line1 = models.CharField(max_length=255, blank=True)
    delivery_address_line2 = models.CharField(max_length=255, blank=True)
    delivery_city = models.CharField(max_length=100, blank=True)
    delivery_postcode = models.CharField(max_length=20, blank=True)
    delivery_formatted_address = models.CharField(max_length=255, blank=True)
    delivery_place_id = models.CharField(max_length=255, blank=True)
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_distance_miles = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    
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
    delivery_fee = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
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
    fulfilment_slot_start = models.DateTimeField(null=True, blank=True, db_index=True)
    estimated_ready_time = models.DateTimeField(null=True, blank=True, help_text="Kitchen's estimated ready time")
    actual_ready_time = models.DateTimeField(null=True, blank=True, help_text="When order was actually marked ready")
    accepted_at = models.DateTimeField(null=True, blank=True)
    preparing_started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_orders",
    )
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_orders",
    )
    cancelled_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_orders",
    )
    special_instructions = models.TextField(blank=True)
    staff_notes = models.TextField(blank=True, help_text="Internal kitchen notes")
    handover_notes = models.TextField(blank=True, help_text="Collection/delivery handover notes")
    cancel_reason = models.CharField(max_length=255, blank=True)
    delivery_zone_name = models.CharField(max_length=100, blank=True)
    delivery_eta_minutes = models.PositiveIntegerField(null=True, blank=True)
    delivery_driver = models.ForeignKey(
        "orders.DeliveryDriver",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    
    # Payment (Mollie)
    mollie_payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    personal_data_anonymised_at = models.DateTimeField(null=True, blank=True)
    
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

    @property
    def is_delivery(self):
        return self.service_type == self.ServiceType.DELIVERY

    @property
    def service_time_label(self):
        return "Delivery Time" if self.is_delivery else "Pickup Time"

    @property
    def ready_status_label(self):
        return "Ready to Dispatch" if self.is_delivery else "Ready for Collection"

    @property
    def dispatch_status_label(self):
        return "Out for Delivery"

    @property
    def service_status_display(self):
        if self.status == self.OrderStatus.READY:
            return self.ready_status_label
        if self.status == self.OrderStatus.OUT_FOR_DELIVERY:
            return self.dispatch_status_label
        return self.get_status_display()

    @property
    def requested_service_time(self):
        return self.requested_pickup_time

    @property
    def delivery_address_display(self):
        if self.delivery_formatted_address:
            return self.delivery_formatted_address
        parts = [
            self.delivery_address_line1,
            self.delivery_address_line2,
            self.delivery_city,
            self.delivery_postcode,
        ]
        return ", ".join(part for part in parts if part)
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)
    
    def generate_order_number(self):
        """Generate unique order number."""
        from django.conf import settings
        prefix = getattr(settings, "ORDER_PREFIX", "TN")
        for _ in range(10):
            unique_id = uuid.uuid4().hex[:8].upper()
            candidate = f"{prefix}-{unique_id}"
            if not Order.objects.filter(order_number=candidate).exists():
                return candidate
        return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
    
    def calculate_totals(self):
        """Calculate order totals from items."""
        subtotal = sum(item.line_total for item in self.items.all())
        self.subtotal = subtotal
        self.total_amount = max(Decimal("0.00"), subtotal - self.discount_amount + self.delivery_fee)
        self.save(update_fields=["subtotal", "total_amount", "updated_at"])
    
    def mark_as_paid(self, changed_by=None):
        """Mark order as paid."""
        self.payment_status = self.PaymentStatus.PAID
        self.paid_at = timezone.now()
        update_fields = ["payment_status", "paid_at", "updated_at"]
        self.save(update_fields=update_fields)

        from .fulfilment import confirm_fulfilment_slot
        from .inventory import consume_order_stock

        confirm_fulfilment_slot(self)
        consume_order_stock(self)

        # Auto-confirm if pending
        if self.status == self.OrderStatus.PENDING:
            self.update_status(self.OrderStatus.CONFIRMED, changed_by=changed_by)

    def preparation_time_minutes(self):
        """Return the order prep estimate using the slowest line item."""
        prep_times = []
        for item in self.items.all():
            prep_time = item.preparation_time_minutes
            if not prep_time and item.menu_item_id:
                prep_time = item.menu_item.preparation_time
            if prep_time:
                prep_times.append(max(1, int(prep_time)))
        return max(prep_times, default=default_preparation_time_minutes())

    def calculate_estimated_ready_time(self, base_time=None):
        """Return when this order should be ready based on item prep snapshots."""
        base_time = base_time or timezone.now()
        return base_time + timezone.timedelta(minutes=self.preparation_time_minutes())
    
    def update_status(self, new_status, changed_by=None):
        """Update order status and log the change."""
        old_status = self.status
        if old_status == new_status:
            return

        now = timezone.now()
        self.status = new_status
        update_fields = ["status", "updated_at"]
        
        # Set estimated ready time when confirmed
        if new_status == self.OrderStatus.CONFIRMED and not self.estimated_ready_time:
            self.estimated_ready_time = self.calculate_estimated_ready_time(now)
            update_fields.append("estimated_ready_time")
        if new_status == self.OrderStatus.CONFIRMED and not self.accepted_at:
            self.accepted_at = now
            update_fields.append("accepted_at")
        if new_status == self.OrderStatus.CONFIRMED and changed_by and not self.accepted_by_id:
            self.accepted_by = changed_by
            update_fields.append("accepted_by")
        if new_status == self.OrderStatus.PREPARING and not self.preparing_started_at:
            self.preparing_started_at = now
            update_fields.append("preparing_started_at")
        
        # Set actual ready time
        if new_status == self.OrderStatus.READY and not self.actual_ready_time:
            self.actual_ready_time = now
            update_fields.append("actual_ready_time")
        if new_status == self.OrderStatus.READY and not self.ready_at:
            self.ready_at = now
            update_fields.append("ready_at")
        if new_status == self.OrderStatus.OUT_FOR_DELIVERY and not self.ready_at:
            self.ready_at = now
            update_fields.append("ready_at")
        if new_status == self.OrderStatus.OUT_FOR_DELIVERY and not self.actual_ready_time:
            self.actual_ready_time = now
            update_fields.append("actual_ready_time")
        if new_status == self.OrderStatus.OUT_FOR_DELIVERY and not self.dispatched_at:
            self.dispatched_at = now
            update_fields.append("dispatched_at")
        if new_status == self.OrderStatus.COMPLETED and not self.completed_at:
            self.completed_at = now
            update_fields.append("completed_at")
        if new_status == self.OrderStatus.COMPLETED and changed_by and not self.completed_by_id:
            self.completed_by = changed_by
            update_fields.append("completed_by")
        if new_status == self.OrderStatus.COMPLETED and self.is_delivery and not self.delivered_at:
            self.delivered_at = now
            update_fields.append("delivered_at")
        if new_status == self.OrderStatus.COMPLETED and not self.is_delivery and not self.collected_at:
            self.collected_at = now
            update_fields.append("collected_at")
        if new_status == self.OrderStatus.CANCELLED and not self.cancelled_at:
            self.cancelled_at = now
            update_fields.append("cancelled_at")
        if new_status == self.OrderStatus.CANCELLED and changed_by and not self.cancelled_by_id:
            self.cancelled_by = changed_by
            update_fields.append("cancelled_by")
        
        self.save(update_fields=list(dict.fromkeys(update_fields)))
        
        # Log status change
        OrderStatusHistory.objects.create(
            order=self,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by
        )

        if new_status == self.OrderStatus.CANCELLED and self.payment_status != self.PaymentStatus.PAID:
            from .fulfilment import release_fulfilment_slot
            from .inventory import release_order_stock

            release_fulfilment_slot(self)
            release_order_stock(self)
    
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
    preparation_time_minutes = models.PositiveIntegerField(
        default=default_preparation_time_minutes,
        validators=[MinValueValidator(1)],
        help_text="Snapshot of this item's prep time when the order was placed.",
    )
    
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
        if self._state.adding and self.menu_item:
            self.preparation_time_minutes = self.menu_item.preparation_time
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


class OrderIssue(models.Model):
    """Customer support issue raised against an order."""

    class IssueType(models.TextChoices):
        MISSING_ITEM = "missing_item", "Missing Item"
        WRONG_ITEM = "wrong_item", "Wrong Item"
        LATE_DELIVERY = "late_delivery", "Late Delivery"
        QUALITY = "quality", "Food Quality"
        PAYMENT = "payment", "Payment"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEWING = "reviewing", "Reviewing"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"
        REFUND_REQUESTED = "refund_requested", "Refund Requested"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="issues")
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_issues",
    )
    issue_type = models.CharField(max_length=30, choices=IssueType.choices)
    description = models.TextField()
    requested_refund_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    staff_notes = models.TextField(blank=True)
    refund_request = models.ForeignKey(
        "payments.RefundRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_issues",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["order", "created_at"]),
        ]

    def __str__(self):
        return f"{self.order.order_number} - {self.get_issue_type_display()}"


class FulfilmentCapacityRule(models.Model):
    """Capacity rule for pickup or delivery ordering windows."""

    class ServiceType(models.TextChoices):
        PICKUP = Order.ServiceType.PICKUP, "Pickup"
        DELIVERY = Order.ServiceType.DELIVERY, "Delivery"

    service_type = models.CharField(max_length=20, choices=ServiceType.choices, db_index=True)
    day_of_week = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0)],
        help_text="0=Monday, 6=Sunday.",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveIntegerField(default=15, validators=[MinValueValidator(5)])
    lead_time_minutes = models.PositiveIntegerField(default=15)
    last_order_minutes_before_close = models.PositiveIntegerField(default=15)
    max_orders = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service_type", "day_of_week", "start_time"]
        indexes = [models.Index(fields=["service_type", "day_of_week", "is_active"])]

    def __str__(self):
        return f"{self.get_service_type_display()} day {self.day_of_week} {self.start_time}-{self.end_time}"


class FulfilmentBlackout(models.Model):
    """Date/time blackout for pickup, delivery, or both."""

    class ServiceType(models.TextChoices):
        ALL = "all", "All"
        PICKUP = Order.ServiceType.PICKUP, "Pickup"
        DELIVERY = Order.ServiceType.DELIVERY, "Delivery"

    service_type = models.CharField(max_length=20, choices=ServiceType.choices, default=ServiceType.ALL, db_index=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["service_type", "starts_at", "ends_at", "is_active"])]

    def __str__(self):
        return self.reason or f"Blackout {self.starts_at:%Y-%m-%d %H:%M}"


class FulfilmentSlotReservation(models.Model):
    """Reservation of capacity for an order fulfilment slot."""

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        CONFIRMED = "confirmed", "Confirmed"
        RELEASED = "released", "Released"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="slot_reservation")
    service_type = models.CharField(max_length=20, choices=Order.ServiceType.choices, db_index=True)
    slot_start = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RESERVED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slot_start"]
        indexes = [models.Index(fields=["service_type", "slot_start", "status"])]

    def __str__(self):
        return f"{self.order.order_number} {self.service_type} {self.slot_start:%Y-%m-%d %H:%M}"


class DeliveryZone(models.Model):
    """Delivery pricing and radius rule."""

    name = models.CharField(max_length=100)
    min_distance_miles = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    max_distance_miles = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    estimated_minutes = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["min_distance_miles", "max_distance_miles"]

    def __str__(self):
        return f"{self.name} (£{self.fee})"


class DeliveryDriver(models.Model):
    """Staff-manageable delivery driver."""

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DeliveryRun(models.Model):
    """A sequenced dispatch run for one driver."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        DISPATCHED = "dispatched", "Dispatched"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    driver = models.ForeignKey(DeliveryDriver, on_delete=models.SET_NULL, null=True, blank=True, related_name="runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    planned_departure_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Delivery run #{self.pk or 'new'} ({self.status})"


class DeliveryRunOrder(models.Model):
    """Order position inside a delivery run."""

    run = models.ForeignKey(DeliveryRun, on_delete=models.CASCADE, related_name="run_orders")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery_run_order")
    sequence = models.PositiveIntegerField(default=1)
    eta_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        unique_together = [("run", "sequence")]

    def __str__(self):
        return f"{self.run_id}:{self.sequence} {self.order.order_number}"
