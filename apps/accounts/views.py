"""
Views for the accounts app.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from allauth.account.views import LoginView, SignupView, LogoutView, PasswordResetView

from apps.orders.models import Order

from .forms import UserProfileForm
from .models import CustomerProfile


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
    template = "desktop/accounts/profile.html" if getattr(request, "is_desktop", True) else "accounts/profile.html"
    return render(request, template, context)


@login_required
def order_history(request):
    """View all order history."""
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    template = "desktop/accounts/order_history.html" if getattr(request, "is_desktop", True) else "accounts/order_history.html"
    return render(request, template, {"orders": orders})
