"""
Admin configuration for the orders app.
"""
from django.contrib import admin

from .models import (
    DeliveryDriver,
    DeliveryRun,
    DeliveryRunOrder,
    DeliveryZone,
    FulfilmentBlackout,
    FulfilmentCapacityRule,
    FulfilmentSlotReservation,
    Order,
    OrderIssue,
    OrderItem,
    OrderStatusHistory,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["line_total"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["old_status", "new_status", "changed_by", "created_at"]
    can_delete = False


class OrderIssueInline(admin.TabularInline):
    model = OrderIssue
    extra = 0
    readonly_fields = ["created_at", "updated_at", "resolved_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "service_type",
        "customer_name",
        "customer_phone",
        "status",
        "payment_status",
        "delivery_fee",
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
        "delivery_formatted_address",
        "delivery_place_id",
    ]
    readonly_fields = [
        "order_number",
        "created_at",
        "updated_at",
        "paid_at",
        "personal_data_anonymised_at",
        "payment_reference_display",
        "accepted_at",
        "preparing_started_at",
        "ready_at",
        "dispatched_at",
        "collected_at",
        "delivered_at",
        "completed_at",
        "cancelled_at",
        "delivery_distance_miles",
    ]
    inlines = [OrderItemInline, OrderIssueInline, OrderStatusHistoryInline]
    
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
            "fields": (
                "delivery_address_line1",
                "delivery_address_line2",
                "delivery_city",
                "delivery_postcode",
                "delivery_formatted_address",
                "delivery_place_id",
                "delivery_latitude",
                "delivery_longitude",
                "delivery_distance_miles",
                "delivery_zone_name",
                "delivery_eta_minutes",
                "delivery_driver",
            ),
        }),
        ("Financial", {
            "fields": ("subtotal", "discount_amount", "delivery_fee", "total_amount")
        }),
        ("Details", {
            "fields": (
                "requested_pickup_time",
                "fulfilment_slot_start",
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


@admin.register(OrderIssue)
class OrderIssueAdmin(admin.ModelAdmin):
    list_display = ["order", "user", "issue_type", "status", "requested_refund_amount", "created_at"]
    list_filter = ["issue_type", "status", "created_at"]
    search_fields = ["order__order_number", "user__email", "description", "staff_notes"]
    autocomplete_fields = ["order", "user", "refund_request"]
    readonly_fields = ["created_at", "updated_at", "resolved_at"]


@admin.register(FulfilmentCapacityRule)
class FulfilmentCapacityRuleAdmin(admin.ModelAdmin):
    list_display = ["service_type", "day_of_week", "start_time", "end_time", "slot_minutes", "max_orders", "is_active"]
    list_filter = ["service_type", "day_of_week", "is_active"]
    list_editable = ["slot_minutes", "max_orders", "is_active"]


@admin.register(FulfilmentBlackout)
class FulfilmentBlackoutAdmin(admin.ModelAdmin):
    list_display = ["service_type", "starts_at", "ends_at", "reason", "is_active"]
    list_filter = ["service_type", "is_active", "starts_at"]
    search_fields = ["reason"]


@admin.register(FulfilmentSlotReservation)
class FulfilmentSlotReservationAdmin(admin.ModelAdmin):
    list_display = ["order", "service_type", "slot_start", "status", "created_at"]
    list_filter = ["service_type", "status", "slot_start"]
    search_fields = ["order__order_number"]


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ["name", "min_distance_miles", "max_distance_miles", "fee", "estimated_minutes", "is_active"]
    list_editable = ["fee", "estimated_minutes", "is_active"]


@admin.register(DeliveryDriver)
class DeliveryDriverAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "phone"]


class DeliveryRunOrderInline(admin.TabularInline):
    model = DeliveryRunOrder
    extra = 0


@admin.register(DeliveryRun)
class DeliveryRunAdmin(admin.ModelAdmin):
    list_display = ["id", "driver", "status", "planned_departure_at", "dispatched_at", "completed_at"]
    list_filter = ["status", "driver", "planned_departure_at"]
    inlines = [DeliveryRunOrderInline]


@admin.register(DeliveryRunOrder)
class DeliveryRunOrderAdmin(admin.ModelAdmin):
    list_display = ["run", "sequence", "order", "eta_at", "delivered_at"]
    list_filter = ["run__status"]
    search_fields = ["order__order_number", "run__driver__name"]
