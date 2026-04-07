"""
Admin configuration for the accounts app.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CustomerProfile, User


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
    list_display = ["user", "notifications_enabled", "created_at"]
    list_filter = ["notifications_enabled", "marketing_consent"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    filter_horizontal = ["favorite_items"]
