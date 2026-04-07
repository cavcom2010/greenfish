"""Admin for SMS app."""
from django.contrib import admin

from .models import SMSMessage, SMSSettings


@admin.register(SMSMessage)
class SMSMessageAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "message_type",
        "phone_number",
        "status",
        "created_at",
    ]
    list_filter = ["message_type", "status", "created_at"]
    search_fields = ["user__email", "phone_number", "message"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(SMSSettings)
class SMSSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "enabled",
        "is_configured",
        "twilio_phone_number",
        "send_order_confirmed",
        "send_order_ready",
    ]
    
    def has_add_permission(self, request):
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)
