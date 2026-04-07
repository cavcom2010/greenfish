"""
Core context processors - Cart and common utilities.
"""
from apps.cart.services import CartService


def cart_context(request):
    """Add cart information to template context using CartService."""
    cart = CartService(request)
    
    return {
        "cart_items": cart.get_items(),
        "cart_total": float(cart.get_total()),
        "cart_count": cart.get_count(),
    }
