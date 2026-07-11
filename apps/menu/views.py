"""
Views for the menu app.
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from apps.accounts.models import CustomerProfile
from apps.core.media import get_image_variant_url
from apps.orders.services import selected_service_type

from .models import MenuCategory, MenuItem
from .services import get_recommendations


def menu_list(request):
    """Full menu page. All items are rendered; category/dietary filters and
    search run client-side (menu.js) with the URL kept in sync, so
    ?category= and ?dietary= only seed the initial filter state here."""
    categories = MenuCategory.objects.filter(is_active=True).order_by("sort_order")

    all_items = MenuItem.objects.filter(
        is_available=True
    ).select_related("category").order_by("category__sort_order", "sort_order")

    category_id = request.GET.get("category")
    dietary_filter = (request.GET.get("dietary") or "").strip().lower()
    active_category = MenuCategory.objects.filter(id=category_id).first() if category_id else None

    context = {
        "categories": categories,
        "all_items": all_items,
        "active_category": active_category,
        "dietary_filter": dietary_filter,
        "service_type": selected_service_type(request),
    }

    return render(request, "menu/menu_list.html", context)


def menu_item_detail(request, pk):
    """Get menu item details for modal/ajax."""
    item = get_object_or_404(MenuItem, pk=pk, is_available=True)
    
    # Get recommendations
    recommendations = get_recommendations(item.id, limit=4)
    is_favorite = False
    if request.user.is_authenticated:
        profile = CustomerProfile.objects.filter(user=request.user).first()
        if profile:
            is_favorite = profile.favorite_items.filter(pk=item.pk).exists()
    
    # Return HTML for browser requests (modal), JSON for API requests
    accept_header = request.headers.get("Accept", "")
    is_json_request = "application/json" in accept_header and "text/html" not in accept_header
    
    if request.headers.get("HX-Request") or not is_json_request:
        return render(request, "menu/partials/item_detail.html", {
            "item": item,
            "recommendations": recommendations,
            "is_favorite": is_favorite,
        })
    
    return JsonResponse({
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "price": str(item.price),
        "image": get_image_variant_url(item.image, "card") if item.image else None,
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
        "is_favorite": is_favorite,
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
