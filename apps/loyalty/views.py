"""Views for loyalty app."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.models import SiteSettings
from apps.orders.services import clear_reward_wallet_item, store_reward_wallet_item

from .models import LoyaltyTransaction, RewardWalletItem
from .services import get_user_loyalty_summary


def _loyalty_template(request, template_name):
    """Return desktop or mobile template path."""
    if getattr(request, "is_desktop", True):
        return f"desktop/{template_name}"
    return template_name


@login_required
def rewards_dashboard(request):
    """Main rewards dashboard."""
    summary = get_user_loyalty_summary(request.user)

    context = {
        **summary,
        "title": f"{SiteSettings.get().shop_name} Rewards",
    }
    return render(request, _loyalty_template(request, "loyalty/dashboard.html"), context)


@login_required
def transaction_history(request):
    """Show full transaction history."""
    summary = get_user_loyalty_summary(request.user)

    context = {
        **summary,
        "title": "Points History",
    }
    return render(request, _loyalty_template(request, "loyalty/transactions.html"), context)


@login_required
def refer_friend(request):
    """Refer a friend page."""
    summary = get_user_loyalty_summary(request.user)

    context = {
        **summary,
        "title": "Refer a Friend",
    }
    return render(request, _loyalty_template(request, "loyalty/refer.html"), context)


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
        LoyaltyTransaction.objects.create(
            user=request.user,
            transaction_type=LoyaltyTransaction.TransactionType.BONUS,
            points=wallet_item.points_value,
            description=wallet_item.title,
        )
        wallet_item.mark_used(None)
        messages.success(request, f"{wallet_item.points_value} points added to your account.")
        return redirect("loyalty:dashboard")

    messages.info(request, "This reward is saved in your wallet.")
    return redirect("loyalty:dashboard")


@require_POST
def clear_wallet_item(request):
    """Clear the active checkout wallet reward."""
    clear_reward_wallet_item(request)
    messages.success(request, "Reward removed.")
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect(reverse("loyalty:dashboard"))
