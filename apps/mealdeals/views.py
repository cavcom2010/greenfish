"""Views for meal deals."""
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.services import selected_service_type

from .models import MealDeal


def deal_list(request):
    """Show all active meal deals."""
    deals = MealDeal.objects.filter(is_active=True).prefetch_related("items__options__menu_item")

    context = {
        "deals": deals,
        "title": "Meal Deals",
    }
    template = "desktop/mealdeals/list.html" if getattr(request, "is_desktop", True) else "mealdeals/list.html"
    return render(request, template, context)


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
        "service_type": selected_service_type(request),
    }
    template = "desktop/mealdeals/builder.html" if getattr(request, "is_desktop", True) else "mealdeals/builder.html"
    return render(request, template, context)
