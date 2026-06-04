"""
Admin configuration for the accounts app.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CustomerDataRequest, CustomerProfile, SavedMeal, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "full_name", "phone_number", "is_staff", "is_active", "date_joined"]
    list_filter = ["is_staff", "is_active", "is_superuser"]
    search_fields = ["email", "first_name", "last_name", "phone_number"]
    ordering = ["-date_joined"]
    
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2"),
        }),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "date_of_birth", "notifications_enabled", "marketing_consent", "created_at"]
    list_filter = ["notifications_enabled", "marketing_consent"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    filter_horizontal = ["favorite_items"]


@admin.register(SavedMeal)
class SavedMealAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "item_name", "quantity", "last_added_at", "updated_at"]
    list_filter = ["created_at", "last_added_at"]
    search_fields = ["name", "item_name", "user__email"]
    autocomplete_fields = ["user", "menu_item"]
    readonly_fields = ["created_at", "updated_at", "last_added_at"]


@admin.register(CustomerDataRequest)
class CustomerDataRequestAdmin(admin.ModelAdmin):
    list_display = ["email", "request_type", "status", "requested_at", "completed_at"]
    list_filter = ["request_type", "status", "requested_at"]
    search_fields = ["email", "user__email", "notes"]
    readonly_fields = ["export_payload", "requested_at", "completed_at"]
    actions = ["process_requests"]

    def process_requests(self, request, queryset):
        from .privacy import process_customer_data_request

        for data_request in queryset:
            process_customer_data_request(data_request)

    process_requests.short_description = "Process selected data requests"
