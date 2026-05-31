"""
Views for the accounts app.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from allauth.account.views import LoginView, SignupView, LogoutView, PasswordResetView

from apps.orders.models import Order
from apps.orders.services import add_menu_item_to_cart

from .forms import UserProfileForm
from .models import CustomerProfile
from apps.menu.models import MenuItem


def _desktop_template(template_name, request):
    """Return desktop or mobile template path."""
    if getattr(request, 'is_desktop', True):
        parts = template_name.split('/')
        if len(parts) >= 2:
            return f"desktop/{parts[0]}/{parts[1]}"
    return template_name


# ── Desktop-aware allauth wrappers ──────────────────────────────────────
def desktop_aware_login(request):
    """Login page — desktop-aware."""
    if not getattr(request, 'is_desktop', True):
        from allauth.account.views import LoginView
        return LoginView.as_view()(request)
    from allauth.account.forms import LoginForm
    if request.method == "POST":
        form = LoginForm(request)
        if form.is_valid():
            form.login(request)
            return redirect("core:home")
    else:
        form = LoginForm()
    return render(request, "desktop/account/login.html", {"form": form})


def desktop_aware_signup(request):
    """Signup page — desktop-aware."""
    if not getattr(request, 'is_desktop', True):
        from allauth.account.views import SignupView
        return SignupView.as_view()(request)
    from allauth.account.forms import SignupForm
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(request)
            return redirect("core:home")
    else:
        form = SignupForm()
    return render(request, "desktop/account/signup.html", {"form": form})


def desktop_aware_logout(request):
    """Logout confirmation — desktop-aware."""
    if not getattr(request, 'is_desktop', True):
        from allauth.account.views import LogoutView
        return LogoutView.as_view()(request)
    if request.method == "POST":
        from django.contrib.auth import logout
        logout(request)
        return redirect("core:home")
    return render(request, "desktop/account/logout.html", {})


def desktop_aware_password_reset(request):
    """Password reset — desktop-aware."""
    if not getattr(request, 'is_desktop', True):
        from allauth.account.views import PasswordResetView
        return PasswordResetView.as_view()(request)
    from allauth.account.forms import ResetPasswordForm
    if request.method == "POST":
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            form.save(request)
            return redirect("account_login")
    else:
        form = ResetPasswordForm()
    return render(request, "desktop/account/password_reset.html", {"form": form})


# ── Existing views ──────────────────────────────────────────────────────


@login_required
def profile(request):
    """User profile view."""
    user = request.user
    orders = Order.objects.filter(user=user).prefetch_related("items__menu_item").order_by("-created_at")[:10]

    # Ensure profile exists
    profile, created = CustomerProfile.objects.get_or_create(user=user)
    favorite_items = profile.favorite_items.filter(is_available=True).select_related("category")[:6]

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
        "favorite_items": favorite_items,
    }
    template = "desktop/accounts/profile.html" if getattr(request, "is_desktop", True) else "accounts/profile.html"
    return render(request, template, context)


@login_required
def order_history(request):
    """View all order history."""
    orders = Order.objects.filter(user=request.user).prefetch_related("items__menu_item").order_by("-created_at")
    template = "desktop/accounts/order_history.html" if getattr(request, "is_desktop", True) else "accounts/order_history.html"
    return render(request, template, {"orders": orders})


@login_required
@require_POST
def reorder(request, order_id):
    """Add the available menu items from a past order back into the basket."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items__menu_item"),
        pk=order_id,
        user=request.user,
    )

    added_count = 0
    skipped_count = 0
    for order_item in order.items.all():
        menu_item = order_item.menu_item
        if not menu_item or not menu_item.is_available:
            skipped_count += order_item.quantity
            continue
        add_menu_item_to_cart(
            request,
            menu_item,
            quantity=order_item.quantity,
            modifiers=order_item.modifiers,
        )
        added_count += order_item.quantity

    if added_count:
        messages.success(request, f"Added {added_count} item{'' if added_count == 1 else 's'} from {order.order_number} to your basket.")
        if skipped_count:
            messages.warning(request, "Some unavailable items were not added.")
        return redirect("orders:cart")

    messages.error(request, "None of the items from that order are available right now.")
    return redirect("accounts:order_history")


@login_required
@require_POST
def toggle_favorite(request, item_id):
    """Toggle a menu item in the customer's favourites."""
    item = get_object_or_404(MenuItem, pk=item_id, is_available=True)
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)

    if profile.favorite_items.filter(pk=item.pk).exists():
        profile.favorite_items.remove(item)
        is_favorite = False
        message = "Removed from your favourites."
    else:
        profile.favorite_items.add(item)
        is_favorite = True
        message = "Saved to your favourites."

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"success": True, "is_favorite": is_favorite, "message": message})

    messages.success(request, message)
    return redirect(request.POST.get("next") or "accounts:profile")


@login_required
@require_POST
def add_favorite_to_cart(request, item_id):
    """Add a saved favourite directly to the basket."""
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    item = get_object_or_404(
        profile.favorite_items.filter(is_available=True),
        pk=item_id,
    )
    add_menu_item_to_cart(request, item, quantity=1, modifiers=[])
    messages.success(request, f"Added {item.name} to your basket.")
    return redirect("orders:cart")
