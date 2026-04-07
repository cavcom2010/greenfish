"""Views for meal deals."""
from django.shortcuts import get_object_or_404, redirect, render

from .models import MealDeal


def deal_list(request):
    """Show all active meal deals."""
    deals = MealDeal.objects.filter(is_active=True).prefetch_related("items__options__menu_item")
    
    context = {
        "deals": deals,
        "title": "Meal Deals",
    }
    return render(request, "mealdeals/list.html", context)


def deal_detail(request, deal_id):
    """Show deal builder page."""
    deal = get_object_or_404(
        MealDeal.objects.prefetch_related("items__options__menu_item"),
        id=deal_id,
        is_active=True
    )
    
    context = {
        "deal": deal,
        "title": deal.name,
    }
    return render(request, "mealdeals/builder.html", context)
