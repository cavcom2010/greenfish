"""
Admin configuration for the payments app.
"""
from django.contrib import admin

from .models import Payment, PaymentLog


class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 0
    readonly_fields = ["event_type", "event_data", "created_at"]
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "mollie_payment_id",
        "order",
        "amount",
        "currency",
        "status",
        "mollie_payment_method",
        "created_at",
        "paid_at"
    ]
    list_filter = ["status", "currency", "mollie_payment_method", "created_at"]
    search_fields = ["mollie_payment_id", "order__order_number", "order__customer_email"]
    readonly_fields = ["mollie_payment_id", "created_at", "updated_at", "paid_at"]
    inlines = [PaymentLogInline]
    
    actions = ["refresh_status"]
    
    def refresh_status(self, request, queryset):
        from .services import MolliePaymentService
        service = MolliePaymentService()
        for payment in queryset:
            service.update_payment_status(payment.mollie_payment_id)
    refresh_status.short_description = "Refresh payment status from Mollie"


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ["payment", "event_type", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["payment__mollie_payment_id"]
    readonly_fields = ["payment", "event_type", "event_data", "created_at"]
