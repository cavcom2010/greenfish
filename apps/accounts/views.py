"""
Views for the accounts app.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.orders.models import Order

from .forms import UserProfileForm
from .models import CustomerProfile


@login_required
def profile(request):
    """User profile view."""
    user = request.user
    orders = Order.objects.filter(user=user).order_by("-created_at")[:10]
    
    # Ensure profile exists
    profile, created = CustomerProfile.objects.get_or_create(user=user)
    
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect("accounts:profile")
    else:
        form = UserProfileForm(instance=user)
    
    context = {
        "form": form,
        "orders": orders,
        "profile": profile,
    }
    return render(request, "accounts/profile.html", context)


@login_required
def order_history(request):
    """View all order history."""
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "accounts/order_history.html", {"orders": orders})
