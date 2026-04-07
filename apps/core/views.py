"""
Core views for Tinashe Takeaway.
"""
from django.shortcuts import render

from apps.menu.models import MenuCategory, MenuItem
from apps.offers.models import Offer


def home(request):
    """Home page view with full menu and dietary filters."""
    categories = MenuCategory.objects.filter(is_active=True).order_by("sort_order")
    
    # Get filter parameters
    category_id = request.GET.get("category")
    dietary_filter = request.GET.get("dietary")
    
    # Build base queryset
    items = MenuItem.objects.filter(is_available=True)
    
    # Apply category filter
    if category_id:
        active_category = MenuCategory.objects.filter(id=category_id).first()
        items = items.filter(category_id=category_id)
    else:
        active_category = None
    
    # Apply dietary filter
    if dietary_filter:
        items = items.filter(dietary_tags__contains=[dietary_filter])
    
    items = items.select_related("category").order_by("category__sort_order", "sort_order")
    
    # Get popular items for "Popular Now" section
    popular_items = MenuItem.objects.filter(
        is_available=True, is_popular=True
    ).select_related("category")[:6]
    
    # Get active offers for hero banner
    hero_offers = Offer.objects.filter(
        is_active=True, display_on_hero=True
    ).order_by("-created_at")[:3]
    
    context = {
        "categories": categories,
        "items": items,
        "popular_items": popular_items,
        "active_category": active_category,
        "dietary_filter": dietary_filter,
        "hero_offers": hero_offers,
    }
    return render(request, "core/home.html", context)


def about(request):
    """About page view."""
    return render(request, "core/about.html")


def contact(request):
    """Contact page view."""
    return render(request, "core/contact.html")
