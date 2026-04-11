"""
Admin configuration for the orders app.
"""
from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["line_total"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["old_status", "new_status", "changed_by", "created_at"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "service_type",
        "customer_name",
        "customer_phone",
        "status",
        "payment_status",
        "total_amount",
        "created_at"
    ]
    list_filter = ["service_type", "status", "payment_status", "created_at"]
    search_fields = [
        "order_number",
        "customer_name",
        "customer_phone",
        "customer_email",
        "delivery_address_line1",
        "delivery_postcode",
    ]
    readonly_fields = [
        "order_number",
        "created_at",
        "updated_at",
        "paid_at",
        "payment_reference_display",
        "accepted_at",
        "preparing_started_at",
        "ready_at",
        "dispatched_at",
        "collected_at",
        "delivered_at",
        "completed_at",
        "cancelled_at",
    ]
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    
    fieldsets = (
        ("Order Information", {
            "fields": ("order_number", "status", "payment_status")
        }),
        ("Customer", {
            "fields": ("customer_name", "customer_phone", "customer_email", "user", "service_type")
        }),
        ("Operations", {
            "fields": ("accepted_by", "completed_by", "cancelled_by"),
        }),
        ("Delivery", {
            "fields": ("delivery_address_line1", "delivery_address_line2", "delivery_city", "delivery_postcode"),
        }),
        ("Financial", {
            "fields": ("subtotal", "discount_amount", "total_amount")
        }),
        ("Details", {
            "fields": (
                "requested_pickup_time",
                "estimated_ready_time",
                "actual_ready_time",
                "accepted_at",
                "preparing_started_at",
                "ready_at",
                "dispatched_at",
                "collected_at",
                "delivered_at",
                "completed_at",
                "cancelled_at",
                "special_instructions",
                "staff_notes",
                "handover_notes",
                "cancel_reason",
                "applied_offer",
                "voucher_code",
            )
        }),
        ("Payment", {
            "fields": ("payment_reference_display", "paid_at"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    actions = ["mark_as_confirmed", "mark_as_preparing", "mark_as_ready", "mark_as_completed"]
    
    def mark_as_confirmed(self, request, queryset):
        for order in queryset:
            order.update_status(Order.OrderStatus.CONFIRMED, request.user)
    mark_as_confirmed.short_description = "Mark selected orders as Confirmed"
    
    def mark_as_preparing(self, request, queryset):
        for order in queryset:
            order.update_status(Order.OrderStatus.PREPARING, request.user)
    mark_as_preparing.short_description = "Mark selected orders as Preparing"
    
    def mark_as_ready(self, request, queryset):
        for order in queryset:
            order.update_status(Order.OrderStatus.READY, request.user)
    mark_as_ready.short_description = "Mark selected orders as Ready"
    
    def mark_as_completed(self, request, queryset):
        for order in queryset:
            order.update_status(Order.OrderStatus.COMPLETED, request.user)
    mark_as_completed.short_description = "Mark selected orders as Completed"

    @admin.display(description="Payment Reference")
    def payment_reference_display(self, obj):
        payment = getattr(obj, "payment", None)
        if payment:
            return payment.payment_reference
        return obj.mollie_payment_id or "-"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "item_name", "quantity", "item_price", "line_total"]
    list_filter = ["order__status", "created_at"]
    search_fields = ["order__order_number", "item_name"]
