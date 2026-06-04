"""
Accounts app - Authentication and user management.

This app contains:
- User model (authentication)
- CustomerProfile (business logic)

Note: User is kept here to maintain database compatibility.
In a new project, User would be in 'authentication' app.
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Custom user manager that uses email instead of username."""
    
    use_in_migrations = True
    
    def _create_user(self, email, password, **extra_fields):
        """Create and save a user with the given email and password."""
        if not email:
            raise ValueError("Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user model using email as the unique identifier.
    
    Authentication-only fields here.
    Business data (loyalty points, etc.) is in CustomerProfile.
    """
    
    username = None
    email = models.EmailField(unique=True, verbose_name="email address")
    phone_number = models.CharField(max_length=30, blank=True)
    is_email_verified = models.BooleanField(default=False)
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]
    
    objects = UserManager()
    
    class Meta:
        db_table = "accounts_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
    
    def __str__(self):
        return self.email
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email


class CustomerProfile(models.Model):
    """
    Extended profile for customers - business logic layer.
    
    This separates business data (loyalty, preferences) from
    authentication data (in User model).
    """
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    
    # Preferences & Business Data
    favorite_items = models.ManyToManyField(
        "menu.MenuItem",
        blank=True,
        related_name="favorited_by"
    )
    date_of_birth = models.DateField(null=True, blank=True)
    notifications_enabled = models.BooleanField(default=True)
    marketing_consent = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "accounts_customerprofile"
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"
    
    def __str__(self):
        return f"Profile for {self.user.email}"


class SavedMeal(models.Model):
    """Saved customer meal snapshot, including modifiers."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_meals",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_meal_snapshots",
    )
    name = models.CharField(max_length=120)
    item_name = models.CharField(max_length=160)
    item_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    modifiers = models.JSONField(default=list, blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    last_added_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_added_at", "-updated_at"]
        indexes = [models.Index(fields=["user", "-updated_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "menu_item", "item_name"],
                name="unique_saved_meal_base_item_per_user",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"

    @property
    def is_available(self):
        return bool(self.menu_item and self.menu_item.is_available)


class CustomerDataRequest(models.Model):
    """Customer privacy workflow for export and anonymisation requests."""

    class RequestType(models.TextChoices):
        EXPORT = "export", "Export"
        ANONYMISATION = "anonymisation", "Anonymisation"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_requests",
    )
    email = models.EmailField()
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    export_payload = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["status", "requested_at"])]

    def __str__(self):
        return f"{self.email} {self.request_type} ({self.status})"
