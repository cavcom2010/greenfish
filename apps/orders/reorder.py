"""
Eligibility helpers for customer repeat-order actions.
"""
from django.db.models import Q


def reorderable_order_q():
    """Return the queryset condition for orders that can be ordered again."""
    from .models import Order

    return (
        Q(status=Order.OrderStatus.COMPLETED)
        & Q(payment_status=Order.PaymentStatus.PAID)
        & (
            Q(service_type=Order.ServiceType.PICKUP, collected_at__isnull=False)
            | Q(service_type=Order.ServiceType.DELIVERY, delivered_at__isnull=False)
        )
    )


def reorderable_orders(queryset):
    """Filter an order queryset to orders that are safe to order again."""
    return queryset.filter(reorderable_order_q())


def is_reorderable_order(order):
    """Return True when an order was paid and handed over to the customer."""
    if order.status != order.OrderStatus.COMPLETED:
        return False
    if order.payment_status != order.PaymentStatus.PAID:
        return False
    if order.service_type == order.ServiceType.DELIVERY:
        return order.delivered_at is not None
    return order.collected_at is not None
