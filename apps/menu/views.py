"""
Views for the menu app.
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import MenuCategory, MenuItem
from .services import get_recommendations


def menu_list(request):
    """Menu page with all categories and items."""
    categories = MenuCategory.objects.filter(
        is_active=True
    ).prefetch_related(
        "items"
    ).order_by("sort_order")
    
    # Get category filter from query params
    category_id = request.GET.get("category")
    if category_id:
        active_category = get_object_or_404(MenuCategory, id=category_id)
        items = MenuItem.objects.filter(
            category=active_category,
            is_available=True
        ).order_by("sort_order")
    else:
        active_category = None
        items = MenuItem.objects.filter(
            is_available=True
        ).select_related("category").order_by("category__sort_order", "sort_order")
    
    context = {
        "categories": categories,
        "items": items,
        "active_category": active_category,
    }
    return render(request, "menu/menu_list.html", context)


def menu_item_detail(request, pk):
    """Get menu item details for modal/ajax."""
    item = get_object_or_404(MenuItem, pk=pk, is_available=True)
    
    # Get recommendations
    recommendations = get_recommendations(item.id, limit=4)
    
    # Return HTML for browser requests (modal), JSON for API requests
    accept_header = request.headers.get("Accept", "")
    is_json_request = "application/json" in accept_header and "text/html" not in accept_header
    
    if request.headers.get("HX-Request") or not is_json_request:
        return render(request, "menu/partials/item_detail.html", {
            "item": item,
            "recommendations": recommendations,
        })
    
    return JsonResponse({
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "price": str(item.price),
        "image": item.image.url if item.image else None,
        "preparation_time": item.preparation_time,
        "dietary_tags": item.dietary_tags,
        "modifiers": [
            {"id": m.id, "name": m.name, "price": str(m.price_adjustment)}
            for m in item.modifiers.filter(is_active=True)
        ],
        "recommendations": [
            {"id": r.id, "name": r.name, "price": str(r.price)}
            for r in recommendations
        ],
    })


def category_items(request, category_id):
    """Get items for a specific category (HTMX)."""
    category = get_object_or_404(MenuCategory, pk=category_id, is_active=True)
    items = MenuItem.objects.filter(
        category=category,
        is_available=True
    ).order_by("sort_order")
    
    return render(request, "menu/partials/category_items.html", {
        "category": category,
        "items": items,
    })
