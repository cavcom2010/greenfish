"""
Views for the payments app.
"""
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.orders.models import Order, OrderItem

from .services import MolliePaymentService

logger = logging.getLogger(__name__)


@require_POST
def create_payment(request):
    """Create a payment for checkout."""
    cart = request.session.get("cart", {})
    
    if not cart:
        return JsonResponse({"error": "Cart is empty"}, status=400)
    
    # Get customer details from form
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
    
    # Calculate totals from cart
    from decimal import Decimal
    
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
        from apps.offers.models import VoucherCode
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
    )
    
    # Create order items
    from apps.menu.models import MenuItem
    
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
    
    # Create Mollie payment (or simulate if no API key)
    from django.conf import settings
    
    # Clear cart after creating order
    request.session["cart"] = {}
    request.session.pop("voucher_code", None)
    request.session.modified = True
    
    # Check if Mollie is configured
    if not getattr(settings, "MOLLIE_API_KEY", ""):
        # No Mollie API key - create simulated payment for demo
        from apps.payments.models import Payment
        import uuid
        
        payment = Payment.objects.create(
            order=order,
            mollie_payment_id=f"demo_{uuid.uuid4().hex[:12]}",
            amount=order.total_amount,
            currency=getattr(settings, "CURRENCY", "GBP"),
            status=Payment.Status.PENDING,
            checkout_url=request.build_absolute_uri(
                reverse("payments:demo_checkout", args=[order.order_number])
            ),
        )
        return redirect(payment.checkout_url)
    
    # Real Mollie payment
    service = MolliePaymentService()
    try:
        payment = service.create_payment(order, request)
        return redirect(payment.checkout_url)
        
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        # Cancel the order
        order.status = Order.OrderStatus.CANCELLED
        order.save()
        return JsonResponse({"error": "Payment creation failed"}, status=500)


def payment_return(request, order_number):
    """Handle return from Mollie checkout."""
    order = get_object_or_404(Order, order_number=order_number)
    
    # Update payment status
    if hasattr(order, 'payment'):
        service = MolliePaymentService()
        service.update_payment_status(order.payment.mollie_payment_id)
    
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:confirmation", order_number=order_number)
    else:
        # Payment failed or pending
        return render(request, "payments/payment_status.html", {
            "order": order,
            "status": order.payment_status
        })


@csrf_exempt
@require_POST
def webhook(request):
    """Handle Mollie webhook."""
    # Mollie sends the payment ID as form data
    payment_id = request.POST.get("id")
    
    if not payment_id:
        logger.warning("Webhook received without payment ID")
        return HttpResponse("OK", status=200)
    
    logger.info(f"Webhook received for payment: {payment_id}")
    
    # Update payment status
    service = MolliePaymentService()
    payment = service.update_payment_status(payment_id)
    
    if payment:
        logger.info(f"Payment {payment_id} updated to {payment.status}")
    else:
        logger.warning(f"Payment {payment_id} not found")
    
    # Always return 200 to Mollie
    return HttpResponse("OK", status=200)


def payment_status_api(request, order_number):
    """API endpoint to check payment status."""
    order = get_object_or_404(Order, order_number=order_number)
    
    # Update status from Mollie
    if hasattr(order, 'payment'):
        service = MolliePaymentService()
        service.update_payment_status(order.payment.mollie_payment_id)
        order.refresh_from_db()
    
    return JsonResponse({
        "order_number": order.order_number,
        "status": order.status,
        "payment_status": order.payment_status,
        "paid": order.payment_status == Order.PaymentStatus.PAID
    })


def demo_checkout(request, order_number):
    """Demo checkout page for testing without Mollie API."""
    from django.conf import settings
    from django.shortcuts import render, redirect
    from apps.orders.models import Order
    from apps.payments.models import Payment
    import uuid
    
    order = get_object_or_404(Order, order_number=order_number)
    
    # Get or create payment for this order
    payment, created = Payment.objects.get_or_create(
        order=order,
        defaults={
            'mollie_payment_id': f"demo_{uuid.uuid4().hex[:12]}",
            'amount': order.total_amount,
            'currency': getattr(settings, "CURRENCY", "GBP"),
            'status': Payment.Status.PENDING,
        }
    )
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "pay":
            # Simulate successful payment
            payment.status = Payment.Status.PAID
            payment.save()
            order.mark_as_paid()
            return redirect("orders:confirmation", order_number=order_number)
        
        elif action == "cancel":
            # Cancel the order
            payment.status = Payment.Status.CANCELLED
            payment.save()
            order.status = Order.OrderStatus.CANCELLED
            order.save()
            return redirect("orders:checkout")
    
    return render(request, "payments/demo_checkout.html", {
        "order": order,
        "payment": payment
    })
