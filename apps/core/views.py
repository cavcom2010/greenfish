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
from apps.core.media import get_image_variant_url
from apps.core.models import SiteSettings
from apps.mealdeals.models import MealDeal
from apps.menu.models import MenuCategory, MenuItem
from apps.menu.services import get_popular_menu_items
from apps.offers.models import Offer
from apps.orders.reorder import reorderable_orders
from apps.orders.services import get_cart_summary, selected_service_type


def home(request):
    """Shop-window home page; the full browsable menu lives at menu:menu."""
    categories = MenuCategory.objects.filter(is_active=True).order_by("sort_order")
    service_type = selected_service_type(request)

    # Best sellers from recent paid orders (admin is_popular flag as fallback)
    popular_items = get_popular_menu_items(limit=6)
    hero_rotation_images = [
        get_image_variant_url(item.image, "card") for item in popular_items if item.image
    ]

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

    meal_deals = MealDeal.objects.filter(is_active=True).order_by("deal_price")[:2]

    # Chef's showcase: items of the first active "special" category
    # (e.g. Evergreen Special Roll); hidden when no such category exists.
    signature_items = []
    signature_category = (
        MenuCategory.objects.filter(is_active=True, name__icontains="special")
        .order_by("sort_order")
        .first()
    )
    if signature_category:
        signature_items = list(
            signature_category.items.filter(is_available=True)
            .select_related("category")
            .order_by("sort_order")[:4]
        )

    # Opening-hours strip: the JSONField holds {"0": {"open","close"}, ...}
    # keyed by weekday (0=Monday) or free text; normalise for the template.
    opening_hours_rows = []
    opening_hours_text = ""
    raw_hours = SiteSettings.get().opening_hours
    if isinstance(raw_hours, dict) and raw_hours:
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day_index, name in enumerate(day_names):
            entry = raw_hours.get(str(day_index))
            if isinstance(entry, dict) and entry.get("open") and entry.get("close"):
                opening_hours_rows.append({"day": name, "open": entry["open"], "close": entry["close"]})
            else:
                opening_hours_rows.append({"day": name, "open": "", "close": ""})
    elif raw_hours:
        opening_hours_text = str(raw_hours)

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
        "popular_items": popular_items,
        "favorite_items": favorite_items,
        "recent_orders": recent_orders,
        "hero_offers": hero_offers,
        "service_type": service_type,
        "meal_deals": meal_deals,
        "signature_items": signature_items,
        "opening_hours_rows": opening_hours_rows,
        "opening_hours_text": opening_hours_text,
        "hero_rotation_images": hero_rotation_images,
    }

    return render(request, "core/home.html", context)


def about(request):
    """About page view."""
    return render(request, "core/about.html")


def contact(request):
    """Contact page view."""
    return render(request, "core/contact.html")


def privacy(request):
    """Privacy policy / GDPR information page."""
    return render(request, "core/privacy.html")


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
    return render(request, "core/large_orders.html", context)


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
    from apps.core.services.resend import get_resend_service

    service = get_resend_service()
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

    # Fallback: log it (Resend not configured)
    logging.getLogger(__name__).info("Newsletter signup (no Resend): %s", email)
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
