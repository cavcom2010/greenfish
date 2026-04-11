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
        "provider",
        "payment_reference",
        "order",
        "amount",
        "currency",
        "status",
        "payment_method_label",
        "created_at",
        "paid_at"
    ]
    list_filter = ["provider", "status", "currency", "created_at"]
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
    ]
    inlines = [PaymentLogInline]
    
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
