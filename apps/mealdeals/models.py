"""
Meal deals / combo builder system for Tinashe Takeaway.
"""
from decimal import Decimal

from django.db import models

from apps.core.media import (
    MENU_IMAGE_VALIDATORS,
    get_changed_image_names,
    sync_instance_image_variants,
    validate_changed_image_fields,
)


MEAL_DEAL_IMAGE_VARIANTS = {
    "image": ("card", "hero"),
}


class MealDeal(models.Model):
    """A predefined meal deal/combo."""
    
    class DealType(models.TextChoices):
        COMBO = "combo", "Combo Meal"
        FAMILY = "family", "Family Deal"
        LUNCH = "lunch", "Lunch Special"
        STUDENT = "student", "Student Deal"
        CUSTOM = "custom", "Build Your Own"
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    deal_type = models.CharField(max_length=20, choices=DealType.choices, default=DealType.COMBO)
    
    # Pricing
    original_price = models.DecimalField(max_digits=6, decimal_places=2)
    deal_price = models.DecimalField(max_digits=6, decimal_places=2)
    
    # Display
    image = models.ImageField(upload_to="mealdeals/", blank=True, validators=MENU_IMAGE_VALIDATORS)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    # Limits
    max_per_order = models.PositiveIntegerField(default=5, help_text="Maximum quantity per order")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Meal Deal"
        verbose_name_plural = "Meal Deals"
    
    def __str__(self):
        return f"{self.name} (£{self.deal_price})"
    
    @property
    def display_image(self):
        """Card image: own upload, else the first option's dish photo."""
        if self.image:
            return self.image
        for deal_item in self.items.all():
            for option in deal_item.options.all():
                if option.is_available and option.menu_item.image:
                    return option.menu_item.image
        return None

    @property
    def savings(self):
        return self.original_price - self.deal_price
    
    @property
    def savings_percent(self):
        if self.original_price > 0:
            return int((self.savings / self.original_price) * 100)
        return 0

    def save(self, *args, **kwargs):
        changed_images = get_changed_image_names(self, MEAL_DEAL_IMAGE_VARIANTS.keys())
        validate_changed_image_fields(self, changed_images)
        super().save(*args, **kwargs)
        sync_instance_image_variants(self, MEAL_DEAL_IMAGE_VARIANTS, changed_images)


class MealDealItem(models.Model):
    """An item slot in a meal deal (e.g., "Choose 1 Main")."""
    
    deal = models.ForeignKey(
        MealDeal,
        on_delete=models.CASCADE,
        related_name="items"
    )
    name = models.CharField(max_length=100, help_text="e.g., 'Choose 1 Main'")
    description = models.CharField(max_length=255, blank=True)
    
    # Selection limits
    min_quantity = models.PositiveIntegerField(default=1)
    max_quantity = models.PositiveIntegerField(default=1)
    
    sort_order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ["sort_order"]
        verbose_name = "Meal Deal Item"
        verbose_name_plural = "Meal Deal Items"
    
    def __str__(self):
        return f"{self.deal.name} - {self.name}"


class MealDealOption(models.Model):
    """A specific menu item that can be chosen for a deal item slot."""
    
    deal_item = models.ForeignKey(
        MealDealItem,
        on_delete=models.CASCADE,
        related_name="options"
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.CASCADE,
        related_name="deal_options"
    )
    
    # Optional upgrade price
    upgrade_price = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Extra cost for this option (0 = included)"
    )
    
    is_available = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Meal Deal Option"
        verbose_name_plural = "Meal Deal Options"
    
    def __str__(self):
        return f"{self.menu_item.name} in {self.deal_item.name}"


