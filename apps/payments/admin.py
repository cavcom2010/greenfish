"""
Admin configuration for the payments app.
"""
from django.contrib import admin

from .models import ManualPaymentReceipt, Payment, PaymentLog, PaymentWebhookEvent, RefundRequest


class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 0
    readonly_fields = ["event_type", "event_data", "created_at"]
    can_delete = False


class ManualPaymentReceiptInline(admin.StackedInline):
    model = ManualPaymentReceipt
    extra = 0
    max_num = 0
    can_delete = False
    readonly_fields = [
        "method",
        "amount_due",
        "amount_received",
        "change_given",
        "reference_code",
        "notes",
        "recorded_by",
        "request_ip",
        "user_agent",
        "recorded_at",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "provider",
        "payment_reference",
        "order",
        "amount",
        "currency",
        "status",
        "payment_method_label",
        "created_at",
        "paid_at",
        "expires_at",
    ]
    list_filter = ["provider", "status", "currency", "created_at", "expires_at"]
    search_fields = [
        "external_payment_id",
        "mollie_payment_id",
        "order__order_number",
        "order__customer_email",
    ]
    readonly_fields = [
        "provider",
        "external_payment_id",
        "mollie_payment_id",
        "created_at",
        "updated_at",
        "paid_at",
        "expires_at",
    ]
    inlines = [ManualPaymentReceiptInline, PaymentLogInline]
    
    actions = ["refresh_status"]
    
    def refresh_status(self, request, queryset):
        from .services import refresh_payment_status

        for payment in queryset:
            refresh_payment_status(payment)
    refresh_status.short_description = "Refresh payment status from provider"


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ["payment", "event_type", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["payment__external_payment_id", "payment__mollie_payment_id"]
    readonly_fields = ["payment", "event_type", "event_data", "created_at"]


@admin.register(ManualPaymentReceipt)
class ManualPaymentReceiptAdmin(admin.ModelAdmin):
    list_display = [
        "payment",
        "method",
        "amount_due",
        "amount_received",
        "change_given",
        "reference_code",
        "recorded_by",
        "recorded_at",
    ]
    list_filter = ["method", "recorded_at", "recorded_by"]
    search_fields = [
        "payment__external_payment_id",
        "payment__order__order_number",
        "reference_code",
        "recorded_by__email",
    ]
    readonly_fields = [
        "payment",
        "method",
        "amount_due",
        "amount_received",
        "change_given",
        "reference_code",
        "notes",
        "recorded_by",
        "request_ip",
        "user_agent",
        "recorded_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ["provider", "event_id", "event_type", "payment", "processed_at", "created_at"]
    list_filter = ["provider", "event_type", "processed_at", "created_at"]
    search_fields = ["event_id", "payment__external_payment_id", "payment__order__order_number"]
    readonly_fields = ["provider", "event_id", "event_type", "payment", "payload", "processed_at", "created_at"]


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display = ["payment", "amount", "reason", "status", "requested_by", "requested_at", "processed_at"]
    list_filter = ["status", "requested_at", "processed_at"]
    search_fields = ["payment__external_payment_id", "payment__order__order_number", "reason"]
    readonly_fields = ["status", "provider_reference", "error_message", "requested_at", "processed_at"]
    actions = ["process_refunds"]

    def process_refunds(self, request, queryset):
        from .services import process_refund_request

        for refund in queryset:
            process_refund_request(refund)

    process_refunds.short_description = "Process selected refund requests"
