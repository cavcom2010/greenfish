"""
Views for the offers app.
"""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.orders.services import clear_selected_offer, selected_offer_id, store_selected_offer
from .models import Offer


def _active_offer_queryset():
    now = timezone.now()
    return Offer.objects.filter(
        is_active=True,
        start_date__lte=now,
        end_date__gte=now,
    ).order_by("display_order", "-created_at")


def _redirect_target(request, fallback):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback


def offer_list(request):
    """List all active offers."""
    offers = [offer for offer in _active_offer_queryset() if offer.is_available_for_user(request.user)]

    context = {
        "offers": offers,
    }
    template = "desktop/offers/offer_list.html" if getattr(request, "is_desktop", True) else "offers/offer_list.html"
    return render(request, template, context)


def offer_detail(request, pk):
    """Offer detail page."""
    offer = get_object_or_404(_active_offer_queryset(), pk=pk)
    if not offer.is_available_for_user(request.user):
        raise Http404("Offer is no longer available.")

    template = "desktop/offers/offer_detail.html" if getattr(request, "is_desktop", True) else "offers/offer_detail.html"
    return render(
        request,
        template,
        {
            "offer": offer,
            "offer_selected": selected_offer_id(request) == offer.id,
            "offer_can_activate": offer.supports_checkout_discount(),
        },
    )


@require_POST
def activate_offer(request, pk):
    """Activate an offer for the current session."""
    offer = get_object_or_404(_active_offer_queryset(), pk=pk)
    next_url = _redirect_target(request, reverse("menu:menu"))

    if not offer.is_available_for_user(request.user):
        messages.error(request, "This offer is no longer available.")
        return redirect(next_url)

    if not offer.supports_checkout_discount():
        messages.error(request, "This offer is not available for online checkout yet.")
        return redirect(next_url)

    store_selected_offer(request, offer)
    messages.success(
        request,
        f"{offer.name} is active and will apply automatically to eligible basket items.",
    )
    return redirect(next_url)


@require_POST
def clear_offer(request):
    """Remove the active offer from the session."""
    clear_selected_offer(request)
    messages.success(request, "Offer removed.")
    return redirect(_redirect_target(request, reverse("offers:list")))
