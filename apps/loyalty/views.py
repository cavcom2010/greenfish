"""Views for loyalty app."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import get_user_loyalty_summary


@login_required
def rewards_dashboard(request):
    """Main rewards dashboard."""
    summary = get_user_loyalty_summary(request.user)
    
    context = {
        **summary,
        "title": f"{SiteSettings.get().shop_name} Rewards",
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
    
    context = {
        **summary,
        "title": "Refer a Friend",
    }
    return render(request, "loyalty/refer.html", context)
