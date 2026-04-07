"""
Menu models for Tinashe Zimbabwean Kitchen.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class MenuCategory(models.Model):
    """Menu category (e.g., Mains, Sides, Drinks)."""
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Emoji or icon class")
    image = models.ImageField(upload_to="menu/categories/", blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Menu Category"
        verbose_name_plural = "Menu Categories"
        ordering = ["sort_order", "name"]
    
    def __str__(self):
        return self.name


class MenuModifier(models.Model):
    """Modifier that can be added to menu items (e.g., Extra cheese)."""
    
    name = models.CharField(max_length=100)
    price_adjustment = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Menu Modifier"
        verbose_name_plural = "Menu Modifiers"
        ordering = ["name"]
    
    def __str__(self):
        if self.price_adjustment > 0:
            return f"{self.name} (+£{self.price_adjustment})"
        return self.name


class MenuItem(models.Model):
    """Individual menu item."""
    
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.CASCADE,
        related_name="items"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    image = models.ImageField(upload_to="menu/items/", blank=True)
    
    # Availability & Inventory
    is_available = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)
    
    # Stock Management (for real-time inventory)
    track_stock = models.BooleanField(default=False, help_text="Enable stock tracking for this item")
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Current stock level")
    low_stock_threshold = models.PositiveIntegerField(default=5, help_text="Alert when stock below this")
    
    @property
    def in_stock(self):
        """Check if item is in stock."""
        if not self.track_stock:
            return True
        return self.stock_quantity > 0
    
    @property
    def is_low_stock(self):
        """Check if item is running low."""
        if not self.track_stock:
            return False
        return self.stock_quantity <= self.low_stock_threshold
    
    preparation_time = models.PositiveIntegerField(
        default=15,
        help_text="Estimated preparation time in minutes"
    )
    
    # Dietary Information
    dietary_tags = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g., ['vegetarian', 'gluten-free', 'spicy', 'halal', 'vegan']"
    )
    allergens = models.JSONField(
        default=list,
        blank=True,
        help_text="e.g., ['nuts', 'dairy', 'gluten', 'shellfish']"
    )
    
    # Nutritional Information (per serving)
    calories = models.PositiveIntegerField(null=True, blank=True, help_text="kcal")
    protein = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="grams")
    carbs = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="grams")
    fat = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="grams")
    salt = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="grams")
    
    modifiers = models.ManyToManyField(
        MenuModifier,
        blank=True,
        related_name="menu_items"
    )
    
    sort_order = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Menu Item"
        verbose_name_plural = "Menu Items"
        ordering = ["category", "sort_order", "name"]
    
    def __str__(self):
        return f"{self.name} ({self.category.name})"
    
    @property
    def dietary_tags_display(self):
        """Return dietary tags as a comma-separated string."""
        return ", ".join(self.dietary_tags) if self.dietary_tags else ""
