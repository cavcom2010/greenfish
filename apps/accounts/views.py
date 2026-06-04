"""
Views for the accounts app.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.orders.access import order_customer_url, request_has_order_token
from apps.orders.models import Order, OrderItem
from apps.orders.reorder import is_reorderable_order, reorderable_orders
from apps.orders.services import add_menu_item_to_cart

from apps.loyalty.services import get_user_loyalty_summary

from .forms import CustomerProfileForm, UserProfileForm
from .models import CustomerProfile, SavedMeal
from apps.menu.models import MenuItem


def _desktop_template(template_name, request):
    """Return desktop or mobile template path."""
    if getattr(request, 'is_desktop', True):
        parts = template_name.split('/')
        if len(parts) >= 2:
            return f"desktop/{parts[0]}/{parts[1]}"
    return template_name


def _safe_next_redirect(request, fallback_url_name):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback_url_name)


# ── Desktop-aware allauth wrappers ──────────────────────────────────────
def desktop_aware_login(request):
    """Login page — desktop-aware."""
    if not getattr(request, 'is_desktop', True):
        from allauth.account.views import LoginView
        return LoginView.as_view()(request)
    from allauth.account.forms import LoginForm
    if request.method == "POST":
        form = LoginForm(request.POST, request=request)
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
    saved_meals = SavedMeal.objects.filter(user=user).select_related("menu_item")[:8]

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user)
        profile_form = CustomerProfileForm(request.POST, instance=profile)
        if form.is_valid() and profile_form.is_valid():
            form.save()
            profile_form.save()
            return redirect("accounts:profile")
    else:
        form = UserProfileForm(instance=user)
        profile_form = CustomerProfileForm(instance=profile)

    context = {
        "form": form,
        "profile_form": profile_form,
        "orders": orders,
        "profile": profile,
        "favorite_items": favorite_items,
        "saved_meals": saved_meals,
    }
    template = "desktop/accounts/profile.html" if getattr(request, "is_desktop", True) else "accounts/profile.html"
    return render(request, template, context)


@login_required
def app_home(request):
    """Account home designed as the installed-app start screen."""
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    recent_orders = (
        reorderable_orders(Order.objects.filter(user=request.user))
        .prefetch_related("items__menu_item")
        .order_by("-created_at")[:5]
    )
    active_order = (
        Order.objects.filter(user=request.user)
        .exclude(status__in=[Order.OrderStatus.COMPLETED, Order.OrderStatus.CANCELLED])
        .order_by("-created_at")
        .first()
    )
    saved_meals = SavedMeal.objects.filter(user=request.user).select_related("menu_item")[:8]
    favorite_items = profile.favorite_items.filter(is_available=True).select_related("category")[:6]
    rewards = get_user_loyalty_summary(request.user)

    context = {
        "profile": profile,
        "recent_orders": recent_orders,
        "active_order": active_order,
        "saved_meals": saved_meals,
        "favorite_items": favorite_items,
        **rewards,
    }
    template = "desktop/accounts/app_home.html" if getattr(request, "is_desktop", True) else "accounts/app_home.html"
    return render(request, template, context)


@login_required
def order_history(request):
    """View all order history."""
    base_orders = Order.objects.filter(user=request.user)
    orders = base_orders.prefetch_related("items__menu_item").order_by("-created_at")
    date_filter = request.GET.get("date", "all")
    status_filter = request.GET.get("status", "all")
    service_filter = request.GET.get("service", "all")

    now = timezone.now()
    if date_filter == "30d":
        orders = orders.filter(created_at__gte=now - timezone.timedelta(days=30))
    elif date_filter == "6m":
        orders = orders.filter(created_at__gte=now - timezone.timedelta(days=182))
    elif date_filter.startswith("year:"):
        try:
            orders = orders.filter(created_at__year=int(date_filter.split(":", 1)[1]))
        except (TypeError, ValueError):
            date_filter = "all"

    valid_statuses = {choice for choice, _ in Order.OrderStatus.choices}
    if status_filter != "all" and status_filter in valid_statuses:
        orders = orders.filter(status=status_filter)
    elif status_filter != "all":
        status_filter = "all"

    valid_services = {choice for choice, _ in Order.ServiceType.choices}
    if service_filter != "all" and service_filter in valid_services:
        orders = orders.filter(service_type=service_filter)
    elif service_filter != "all":
        service_filter = "all"

    paginator = Paginator(orders, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    filter_query = request.GET.copy()
    filter_query.pop("page", None)
    filter_query_string = filter_query.urlencode()
    order_years = [year.year for year in base_orders.dates("created_at", "year", order="DESC")]
    date_options = [
        ("all", "All dates"),
        ("30d", "Last 30 days"),
        ("6m", "Last 6 months"),
        *[(f"year:{year}", str(year)) for year in order_years],
    ]

    context = {
        "orders": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "date_filter": date_filter,
        "status_filter": status_filter,
        "service_filter": service_filter,
        "status_choices": Order.OrderStatus.choices,
        "service_choices": Order.ServiceType.choices,
        "date_options": date_options,
        "filter_query_string": filter_query_string,
    }
    template = "desktop/accounts/order_history.html" if getattr(request, "is_desktop", True) else "accounts/order_history.html"
    return render(request, template, context)


@login_required
@require_POST
def claim_guest_order(request, order_number):
    """Attach a token-authorised guest order to the logged-in customer's account."""
    order = get_object_or_404(Order, order_number=order_number)
    if not request_has_order_token(request, order):
        from django.http import Http404

        raise Http404("Order not found")
    if order.user_id:
        messages.info(request, "That order is already linked to an account.")
        return redirect(order_customer_url("orders:tracking", order))
    if order.customer_email and order.customer_email.lower() != request.user.email.lower():
        from django.http import Http404

        raise Http404("Order not found")

    order.user = request.user
    order.save(update_fields=["user", "updated_at"])
    messages.success(request, f"{order.order_number} has been added to your account.")
    return redirect(order_customer_url("orders:tracking", order))


@login_required
@require_POST
def reorder(request, order_id):
    """Add the available menu items from a past order back into the basket."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items__menu_item"),
        pk=order_id,
        user=request.user,
    )
    if not is_reorderable_order(order):
        messages.error(request, "Only completed paid orders can be ordered again.")
        return redirect("accounts:order_history")

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
    return redirect(_safe_next_redirect(request, "accounts:profile"))


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


@login_required
@require_POST
def save_order_item_meal(request, order_item_id):
    """Save a past order line, including modifiers, as a reusable meal."""
    order_item = get_object_or_404(
        OrderItem.objects.select_related("order", "menu_item"),
        pk=order_item_id,
        order__user=request.user,
    )
    if not is_reorderable_order(order_item.order):
        messages.error(request, "Meals can only be saved from completed paid orders.")
        return redirect("accounts:order_history")

    menu_item = order_item.menu_item
    image_url = ""
    if menu_item and getattr(menu_item, "image", None):
        try:
            image_url = menu_item.image.url
        except ValueError:
            image_url = ""

    saved_meal, created = SavedMeal.objects.update_or_create(
        user=request.user,
        menu_item=menu_item,
        item_name=order_item.item_name,
        defaults={
            "name": request.POST.get("name", "").strip() or order_item.item_name,
            "item_price": order_item.item_price,
            "quantity": order_item.quantity,
            "modifiers": order_item.modifiers,
            "image_url": image_url,
        },
    )
    messages.success(request, f"{saved_meal.name} {'saved' if created else 'updated'} in your favourites.")
    return redirect(_safe_next_redirect(request, "accounts:app_home"))


@login_required
@require_POST
def add_saved_meal_to_cart(request, saved_meal_id):
    """Add a saved meal snapshot to the basket."""
    saved_meal = get_object_or_404(SavedMeal.objects.select_related("menu_item"), pk=saved_meal_id, user=request.user)
    if not saved_meal.is_available:
        messages.error(request, "That saved meal is not available right now.")
        return redirect("accounts:app_home")

    add_menu_item_to_cart(
        request,
        saved_meal.menu_item,
        quantity=saved_meal.quantity,
        modifiers=saved_meal.modifiers,
    )
    from django.utils import timezone

    saved_meal.last_added_at = timezone.now()
    saved_meal.save(update_fields=["last_added_at", "updated_at"])
    messages.success(request, f"Added {saved_meal.name} to your basket.")
    return redirect("orders:cart")
