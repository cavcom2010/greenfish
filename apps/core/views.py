"""
Core views for Tinashe Takeaway.
"""
import logging

from django.contrib import messages
from django.db import connection
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import CustomerProfile
from apps.core.forms import LargeOrderRequestForm
from apps.menu.models import MenuCategory, MenuItem
from apps.offers.models import Offer
from apps.orders.reorder import reorderable_orders
from apps.orders.services import get_cart_summary, selected_service_type


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
    all_items = MenuItem.objects.filter(is_available=True).select_related("category").order_by("category__sort_order", "sort_order")
    items = all_items

    # Apply category filter
    if category_id:
        active_category = MenuCategory.objects.filter(id=category_id).first()
        items = items.filter(category_id=category_id)
    else:
        active_category = None

    # Apply dietary filter
    if dietary_filter:
        items, dietary_filter = _filter_items_by_dietary_tag(items, dietary_filter)

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

    favorite_items = []
    recent_orders = []
    if request.user.is_authenticated:
        profile = CustomerProfile.objects.filter(user=request.user).first()
        if profile:
            favorite_items = profile.favorite_items.filter(is_available=True).select_related("category")[:6]
        recent_orders = (
            reorderable_orders(request.user.orders.prefetch_related("items__menu_item"))
            .filter(items__menu_item__is_available=True)
            .distinct()
            .order_by("-created_at")[:3]
        )

    context = {
        "categories": categories,
        "items": items,
        "all_items": all_items,
        "popular_items": popular_items,
        "favorite_items": favorite_items,
        "recent_orders": recent_orders,
        "active_category": active_category,
        "dietary_filter": dietary_filter,
        "hero_offers": hero_offers,
        "service_type": service_type,
    }

    return render(request, "core/home.html", context)


def about(request):
    """About page view."""
    template = "desktop/core/about.html" if getattr(request, "is_desktop", True) else "core/about.html"
    return render(request, template)


def contact(request):
    """Contact page view."""
    template = "desktop/core/contact.html" if getattr(request, "is_desktop", True) else "core/contact.html"
    return render(request, template)


def _large_order_initial(request):
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return {"service_type": selected_service_type(request)}

    return {
        "name": getattr(user, "full_name", "") or user.get_full_name() or user.email,
        "phone": getattr(user, "phone_number", ""),
        "email": user.email,
        "service_type": selected_service_type(request),
    }


def _large_order_basket_snapshot(request):
    summary = get_cart_summary(request.session.get("cart", {}), user=request.user)
    return {
        "items": [
            {
                "name": item["name"],
                "quantity": item["quantity"],
                "price": str(item["price"]),
                "line_total": str(item["line_total"]),
                "modifiers": item.get("modifiers", []),
            }
            for item in summary["items"]
        ],
        "subtotal": str(summary["subtotal"]),
        "discount": str(summary["discount"]),
        "total": str(summary["total"]),
    }, summary["total"]


def large_order_request(request):
    """Capture party, corporate, and catering-size order enquiries."""
    initial = _large_order_initial(request)
    basket_snapshot, estimated_total = _large_order_basket_snapshot(request)
    if basket_snapshot["items"]:
        initial.setdefault(
            "requested_items",
            "\n".join(f"{item['quantity']} x {item['name']}" for item in basket_snapshot["items"]),
        )

    if request.method == "POST":
        form = LargeOrderRequestForm(request.POST)
        if form.is_valid():
            large_order = form.save(commit=False)
            if request.user.is_authenticated:
                large_order.user = request.user
            large_order.basket_snapshot = basket_snapshot
            large_order.estimated_total = estimated_total
            large_order.save()
            from apps.core.customer_notifications import enqueue_large_order_request_received

            enqueue_large_order_request_received(large_order)
            messages.success(request, "Large order request sent. The shop will confirm availability, timing, and payment with you.")
            return redirect("core:large_orders")
    else:
        form = LargeOrderRequestForm(initial=initial)

    context = {
        "form": form,
        "basket_snapshot": basket_snapshot,
        "estimated_total": estimated_total,
        "service_type": selected_service_type(request),
    }
    template = "desktop/core/large_orders.html" if getattr(request, "is_desktop", True) else "core/large_orders.html"
    return render(request, template, context)


@require_GET
def health(request):
    """Minimal health endpoint for deployment checks and monitors."""
    payload = {
        "status": "ok",
        "database": "ok",
        "service": "greenfish",
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


@require_POST
def newsletter_signup(request):
    """Handle newsletter sign-up via HTMX."""
    email = request.POST.get("email", "").strip()
    if not email:
        return HttpResponse(
            '<p style="color:var(--error);font-size:0.8rem;margin-top:0.5rem;">Please enter your email.</p>',
            content_type="text/html",
        )

    # If Sender.net is configured, add the contact
    from apps.core.services.sender_net import get_sender_service

    service = get_sender_service()
    if service:
        result = service.add_contact(email, name="", fields={"source": "website_footer"})
        if result.success:
            return HttpResponse(
                '<p style="color:var(--success);font-size:0.8rem;margin-top:0.5rem;">✓ Subscribed! Check your inbox.</p>',
                content_type="text/html",
            )
        return HttpResponse(
            f'<p style="color:var(--error);font-size:0.8rem;margin-top:0.5rem;">{result.error or "Could not subscribe. Please try again."}</p>',
            content_type="text/html",
        )

    # Fallback: log it (Sender.net not configured)
    logging.getLogger(__name__).info("Newsletter signup (no Sender.net): %s", email)
    return HttpResponse(
        '<p style="color:var(--success);font-size:0.8rem;margin-top:0.5rem;">✓ Thanks! We\'ll keep you updated.</p>',
        content_type="text/html",
    )


@require_POST
def record_cookie_consent(request):
    """Record the user's cookie consent preference."""
    preference = request.POST.get("preference", "")
    if preference in ("all", "essential"):
        response = JsonResponse({"status": "ok", "preference": preference})
        response.set_cookie("cookie_consent", preference, max_age=365 * 24 * 60 * 60, httponly=False)
        logging.getLogger(__name__).info("Cookie consent recorded: %s", preference)
        return response
    return JsonResponse({"status": "error"}, status=400)
