"""
Core views for Tinashe Takeaway.
"""
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.menu.models import MenuCategory, MenuItem
from apps.offers.models import Offer
from apps.orders.services import selected_service_type


def _filter_items_by_dietary_tag(queryset, dietary_filter):
    """Filter dietary tags across database backends.

    PostgreSQL supports JSON containment directly. SQLite does not, so fall
    back to a small Python-side pass over the candidate IDs.
    """
    normalized_filter = (dietary_filter or "").strip().lower()
    if not normalized_filter:
        return queryset, ""

    if getattr(connection.features, "supports_json_field_contains", False):
        return queryset.filter(dietary_tags__contains=[normalized_filter]), normalized_filter

    matching_ids = [
        item_id
        for item_id, dietary_tags in queryset.values_list("id", "dietary_tags")
        if any(str(tag).strip().lower() == normalized_filter for tag in (dietary_tags or []))
    ]
    if not matching_ids:
        return queryset.none(), normalized_filter

    return queryset.filter(id__in=matching_ids), normalized_filter


def home(request):
    """Home page view with full menu and dietary filters."""
    categories = MenuCategory.objects.filter(is_active=True).order_by("sort_order")
    service_type = selected_service_type(request)

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
        items, dietary_filter = _filter_items_by_dietary_tag(items, dietary_filter)

    items = items.select_related("category").order_by("category__sort_order", "sort_order")

    # Get popular items for "Popular Now" section
    popular_items = MenuItem.objects.filter(
        is_available=True, is_popular=True
    ).select_related("category")[:6]

    # Get active offers for hero banner
    now = timezone.now()
    hero_offers = [
        offer
        for offer in Offer.objects.filter(
            is_active=True,
            display_on_hero=True,
            start_date__lte=now,
            end_date__gte=now,
        ).order_by("-created_at")
        if offer.is_valid()
    ][:3]

    context = {
        "categories": categories,
        "items": items,
        "popular_items": popular_items,
        "active_category": active_category,
        "dietary_filter": dietary_filter,
        "hero_offers": hero_offers,
        "service_type": service_type,
    }

    template = "desktop/core/home.html" if getattr(request, "is_desktop", True) else "core/home.html"
    return render(request, template, context)


def about(request):
    """About page view."""
    template = "desktop/core/about.html" if getattr(request, "is_desktop", True) else "core/about.html"
    return render(request, template)


def contact(request):
    """Contact page view."""
    template = "desktop/core/contact.html" if getattr(request, "is_desktop", True) else "core/contact.html"
    return render(request, template)


@require_GET
def health(request):
    """Minimal health endpoint for deployment checks and monitors."""
    payload = {
        "status": "ok",
        "database": "ok",
        "service": "two_fish",
        "timestamp": timezone.now().isoformat(),
    }

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        payload["status"] = "degraded"
        payload["database"] = "error"
        return JsonResponse(payload, status=503)

    return JsonResponse(payload)
