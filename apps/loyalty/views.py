"""Views for loyalty app."""
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.models import SiteSettings
from apps.offers.models import Offer
from apps.orders.services import clear_reward_wallet_item, store_reward_wallet_item

from .models import LoyaltySettings, LoyaltyTransaction, RewardWalletItem
from .services import get_user_loyalty_summary


def _active_offers(user):
    now = timezone.now()
    return [
        offer for offer in Offer.objects.filter(
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
        ).order_by("display_order", "-created_at")
        if offer.is_available_for_user(user)
    ]


def rewards_dashboard(request):
    """Unified Rewards hub — loyalty dashboard + public offers.

    Logged-out visitors get a public join teaser instead of a login wall,
    so the Rewards tab sells the programme to the people it should convert.
    """
    title = f"{SiteSettings.get().shop_name} Rewards"
    offers = _active_offers(request.user)

    if not request.user.is_authenticated:
        context = {
            "offers": offers,
            "points_per_pound": LoyaltySettings.get().points_per_pound,
            "title": title,
        }
        return render(request, "loyalty/join.html", context)

    summary = get_user_loyalty_summary(request.user)

    context = {
        **summary,
        "offers": offers,
        "title": title,
    }
    return render(request, "loyalty/dashboard.html", context)


@login_required
def transaction_history(request):
    """Show full transaction history."""
    summary = get_user_loyalty_summary(request.user)

    context = {
        **summary,
        "title": "Points History",
    }
    return render(request, "loyalty/transactions.html", context)


@login_required
def refer_friend(request):
    """Refer a friend page."""
    summary = get_user_loyalty_summary(request.user)
    shop_url = getattr(django_settings, "SHOP_URL", "").rstrip("/")

    context = {
        **summary,
        "title": "Refer a Friend",
        "SHOP_URL": shop_url,
    }
    return render(request, "loyalty/refer.html", context)


@login_required
@require_POST
def activate_wallet_item(request, pk):
    """Activate an offer-backed wallet item or claim point-only rewards."""
    wallet_item = get_object_or_404(
        RewardWalletItem.objects.select_related("offer"),
        pk=pk,
        user=request.user,
    )
    if not wallet_item.is_available():
        messages.error(request, "This reward is no longer available.")
        return redirect("loyalty:dashboard")

    if wallet_item.offer:
        store_reward_wallet_item(request, wallet_item)
        messages.success(request, f"{wallet_item.title} is active for your next eligible basket.")
        return redirect("orders:checkout")

    if wallet_item.points_value > 0:
        try:
            with transaction.atomic():
                wallet_item.mark_used(None)
                LoyaltyTransaction.objects.create(
                    user=request.user,
                    transaction_type=LoyaltyTransaction.TransactionType.BONUS,
                    points=wallet_item.points_value,
                    description=wallet_item.title,
                )
        except ValidationError:
            messages.error(request, "This reward has already been claimed.")
            return redirect("loyalty:dashboard")
        messages.success(request, f"{wallet_item.points_value} points added to your account.")
        return redirect("loyalty:dashboard")

    messages.info(request, "This reward is saved in your wallet.")
    return redirect("loyalty:dashboard")


@login_required
@require_POST
def clear_wallet_item(request):
    """Clear the active checkout wallet reward."""
    clear_reward_wallet_item(request)
    messages.success(request, "Reward removed.")
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect(reverse("loyalty:dashboard"))
