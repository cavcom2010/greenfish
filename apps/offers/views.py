"""
Views for the offers app.
"""
from django.shortcuts import render
from django.utils import timezone

from .models import Offer


def offer_list(request):
    """List all active offers."""
    now = timezone.now()
    
    offers = Offer.objects.filter(
        is_active=True,
        start_date__lte=now,
        end_date__gte=now
    ).order_by("display_order", "-created_at")
    
    context = {
        "offers": offers,
    }
    return render(request, "offers/offer_list.html", context)


def offer_detail(request, pk):
    """Offer detail page."""
    offer = Offer.objects.get(pk=pk, is_active=True)
    return render(request, "offers/offer_detail.html", {"offer": offer})
