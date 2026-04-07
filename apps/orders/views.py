"""
Views for the orders app.
"""
import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.menu.models import MenuItem
from apps.offers.models import Offer, VoucherCode

from .models import Order, OrderItem


def cart_view(request):
    """View cart contents."""
    cart = request.session.get("cart", {})
    cart_items = []
    cart_total = Decimal("0.00")
    
    for item_id, item_data in cart.items():
        try:
            quantity = int(item_data.get("quantity", 1))
            price = Decimal(str(item_data.get("price", 0)))
            modifiers = item_data.get("modifiers", [])
            modifiers_total = sum(Decimal(str(m.get("price", 0))) for m in modifiers)
            line_total = (price + modifiers_total) * quantity
            
            cart_items.append({
                "id": item_id,
                "menu_item_id": item_data.get("menu_item_id"),
                "name": item_data.get("name", ""),
                "quantity": quantity,
                "price": price,
                "modifiers": modifiers,
                "line_total": line_total,
            })
            cart_total += line_total
        except (ValueError, TypeError):
            continue
    
    context = {
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": sum(item["quantity"] for item in cart_items),
    }
    return render(request, "orders/cart.html", context)


@require_POST
def add_to_cart(request):
    """Add item to cart."""
    menu_item_id = request.POST.get("menu_item_id")
    quantity = int(request.POST.get("quantity", 1))
    modifiers_json = request.POST.get("modifiers", "[]")
    
    try:
        menu_item = MenuItem.objects.get(pk=menu_item_id, is_available=True)
    except MenuItem.DoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)
    
    # Parse modifiers
    try:
        modifiers = json.loads(modifiers_json) if modifiers_json else []
    except json.JSONDecodeError:
        modifiers = []
    
    # Generate unique cart item ID
    cart_item_id = f"{menu_item_id}_{hash(json.dumps(modifiers, sort_keys=True)) % 10000}"
    
    # Get or create cart
    cart = request.session.get("cart", {})
    
    if cart_item_id in cart:
        # Update quantity if item already in cart
        cart[cart_item_id]["quantity"] += quantity
    else:
        # Add new item
        cart[cart_item_id] = {
            "menu_item_id": menu_item_id,
            "name": menu_item.name,
            "price": str(menu_item.price),
            "quantity": quantity,
            "modifiers": modifiers,
        }
    
    request.session["cart"] = cart
    request.session.modified = True
    
    # Return updated cart fragment for HTMX
    if request.headers.get("HX-Request"):
        return render(request, "orders/partials/cart_button.html", {
            "cart_count": sum(item["quantity"] for item in cart.values())
        })
    
    return JsonResponse({"success": True, "cart_count": sum(item["quantity"] for item in cart.values())})


@require_POST
def update_cart_item(request, item_id):
    """Update cart item quantity."""
    quantity = int(request.POST.get("quantity", 1))
    cart = request.session.get("cart", {})
    
    if item_id in cart:
        if quantity <= 0:
            del cart[item_id]
        else:
            cart[item_id]["quantity"] = quantity
        request.session.modified = True
    
    return redirect("orders:cart")


@require_POST
def remove_from_cart(request, item_id):
    """Remove item from cart."""
    cart = request.session.get("cart", {})
    
    if item_id in cart:
        del cart[item_id]
        request.session.modified = True
    
    if request.headers.get("HX-Request"):
        return render(request, "orders/partials/cart_content.html")
    
    return redirect("orders:cart")


def checkout(request):
    """Checkout page."""
    cart = request.session.get("cart", {})
    
    if not cart:
        return redirect("menu:menu")
    
    # Calculate totals
    cart_items = []
    subtotal = Decimal("0.00")
    
    for item_id, item_data in cart.items():
        try:
            quantity = int(item_data.get("quantity", 1))
            price = Decimal(str(item_data.get("price", 0)))
            modifiers = item_data.get("modifiers", [])
            modifiers_total = sum(Decimal(str(m.get("price", 0))) for m in modifiers)
            line_total = (price + modifiers_total) * quantity
            
            cart_items.append({
                "id": item_id,
                "name": item_data.get("name", ""),
                "quantity": quantity,
                "price": price,
                "modifiers": modifiers,
                "line_total": line_total,
            })
            subtotal += line_total
        except (ValueError, TypeError):
            continue
    
    # Check for voucher code
    discount = Decimal("0.00")
    voucher_error = None
    voucher_code = request.session.get("voucher_code", "")
    
    if voucher_code:
        try:
            voucher = VoucherCode.objects.get(
                code=voucher_code.upper(),
                is_active=True
            )
            if voucher.is_valid():
                discount = voucher.calculate_discount(subtotal)
        except VoucherCode.DoesNotExist:
            voucher_error = "Invalid voucher code"
            request.session.pop("voucher_code", None)
    
    total = subtotal - discount
    
    context = {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "voucher_code": voucher_code,
        "voucher_error": voucher_error,
    }
    return render(request, "orders/checkout.html", context)


@require_POST
def apply_voucher(request):
    """Apply voucher code."""
    code = request.POST.get("code", "").strip().upper()
    
    try:
        voucher = VoucherCode.objects.get(code=code, is_active=True)
        if voucher.is_valid():
            request.session["voucher_code"] = code
            message = "Voucher applied successfully"
        else:
            message = "This voucher code has expired or reached its usage limit"
    except VoucherCode.DoesNotExist:
        message = "Invalid voucher code"
    
    if request.headers.get("HX-Request"):
        return render(request, "orders/partials/voucher_message.html", {
            "message": message
        })
    
    return redirect("orders:checkout")


def order_confirmation(request, order_number):
    """Order confirmation page."""
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, "orders/confirmation.html", {"order": order})


# ==================== DASHBOARD VIEWS ====================

@login_required
def order_board(request):
    """Real-time order board for staff."""
    if not request.user.is_staff:
        return redirect("core:home")
    
    # Get active orders
    orders = Order.objects.filter(
        status__in=["confirmed", "preparing", "ready"]
    ).order_by("created_at")
    
    context = {
        "orders": orders,
        "pending_count": Order.objects.filter(status="pending").count(),
        "confirmed_count": Order.objects.filter(status="confirmed").count(),
        "preparing_count": Order.objects.filter(status="preparing").count(),
        "ready_count": Order.objects.filter(status="ready").count(),
    }
    return render(request, "orders/dashboard/order_board.html", context)


@login_required
def order_list_fragment(request):
    """HTMX fragment for order list."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    status_filter = request.GET.get("status", "")
    
    orders = Order.objects.all()
    if status_filter:
        orders = orders.filter(status=status_filter)
    else:
        orders = orders.filter(status__in=["confirmed", "preparing", "ready"])
    
    orders = orders.order_by("created_at")[:50]
    
    return render(request, "orders/dashboard/_order_list.html", {"orders": orders})


@login_required
@require_POST
def update_order_status(request, order_id):
    """Update order status."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    order = get_object_or_404(Order, pk=order_id)
    new_status = request.POST.get("status")
    
    if new_status in dict(Order.OrderStatus.choices):
        order.update_status(new_status, request.user)
        
        if request.headers.get("HX-Request"):
            return render(request, "orders/dashboard/_order_card.html", {"order": order})
        
        return JsonResponse({"success": True})
    
    return JsonResponse({"error": "Invalid status"}, status=400)


@login_required
def order_detail_modal(request, order_id):
    """Order detail modal for dashboard."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Unauthorized"}, status=403)
    
    order = get_object_or_404(Order, pk=order_id)
    return render(request, "orders/dashboard/_order_detail.html", {"order": order})


@require_POST
def pay_instore(request):
    """Create order for pay in store (cash on collection)."""
    cart = request.session.get("cart", {})
    
    if not cart:
        return JsonResponse({"error": "Cart is empty"}, status=400)
    
    # Get customer details
    customer_name = request.POST.get("customer_name", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()
    customer_email = request.POST.get("customer_email", "").strip()
    special_instructions = request.POST.get("special_instructions", "").strip()
    pickup_minutes = request.POST.get("pickup_time", "15")
    
    # Validate phone number (UK format)
    import re
    phone_clean = customer_phone.replace(" ", "")
    if not re.match(r'^(07\d{9}|\+447\d{9})$', phone_clean):
        return JsonResponse({"error": "Please enter a valid UK mobile number (e.g., 07747055935)"}, status=400)
    
    if not customer_name or not customer_phone:
        return JsonResponse({"error": "Name and phone are required"}, status=400)
    
    # Calculate requested pickup time
    from django.utils import timezone
    try:
        minutes = int(pickup_minutes)
        requested_pickup_time = timezone.now() + timezone.timedelta(minutes=minutes)
    except (ValueError, TypeError):
        requested_pickup_time = timezone.now() + timezone.timedelta(minutes=15)
    
    # Calculate totals
    subtotal = Decimal("0.00")
    order_items_data = []
    
    for item_id, item_data in cart.items():
        try:
            quantity = int(item_data.get("quantity", 1))
            price = Decimal(str(item_data.get("price", 0)))
            modifiers = item_data.get("modifiers", [])
            modifiers_total = sum(Decimal(str(m.get("price", 0))) for m in modifiers)
            
            order_items_data.append({
                "menu_item_id": item_data.get("menu_item_id"),
                "name": item_data.get("name"),
                "price": price,
                "quantity": quantity,
                "modifiers": modifiers,
            })
            
            subtotal += (price + modifiers_total) * quantity
        except (ValueError, TypeError):
            continue
    
    # Check for voucher
    discount = Decimal("0.00")
    voucher_code = request.session.get("voucher_code", "")
    if voucher_code:
        try:
            voucher = VoucherCode.objects.get(code=voucher_code.upper(), is_active=True)
            if voucher.is_valid(request.user if request.user.is_authenticated else None):
                discount = voucher.calculate_discount(subtotal)
        except VoucherCode.DoesNotExist:
            pass
    
    total = subtotal - discount
    
    # Save customer details to user profile if logged in
    if request.user.is_authenticated:
        user = request.user
        name_parts = customer_name.split(" ", 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ""
        user.phone_number = customer_phone
        if customer_email and not user.email:
            user.email = customer_email
        user.save()
    
    # Create order
    order = Order.objects.create(
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        user=request.user if request.user.is_authenticated else None,
        subtotal=subtotal,
        discount_amount=discount,
        total_amount=total,
        voucher_code=voucher_code,
        special_instructions=special_instructions,
        requested_pickup_time=requested_pickup_time,
        payment_status=Order.PaymentStatus.PENDING,
        status=Order.OrderStatus.CONFIRMED,  # Auto-confirm for pay in store
    )
    
    # Create order items
    for item_data in order_items_data:
        menu_item = None
        if item_data["menu_item_id"]:
            try:
                menu_item = MenuItem.objects.get(pk=item_data["menu_item_id"])
            except MenuItem.DoesNotExist:
                pass
        
        OrderItem.objects.create(
            order=order,
            menu_item=menu_item,
            item_name=item_data["name"],
            item_price=item_data["price"],
            quantity=item_data["quantity"],
            modifiers=item_data["modifiers"],
        )
    
    # Clear cart
    request.session["cart"] = {}
    request.session.pop("voucher_code", None)
    request.session.modified = True
    
    # Send SMS confirmation
    try:
        from apps.sms.services import send_order_confirmation
        send_order_confirmation(order)
    except Exception:
        pass
    
    # Send push notification
    try:
        from apps.pwa.services import notify_order_confirmed
        notify_order_confirmed(order)
    except Exception:
        pass
    
    # Redirect to confirmation with pay-in-store flag
    return redirect("orders:confirmation_instore", order_number=order.order_number)


def confirmation_instore(request, order_number):
    """Order confirmation page for pay in store orders."""
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, "orders/confirmation_instore.html", {"order": order})


def order_tracking(request, order_number):
    """Public order tracking page - no login required."""
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, "orders/tracking.html", {"order": order})
