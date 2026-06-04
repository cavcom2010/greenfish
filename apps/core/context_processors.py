"""
Core context processors - Cart and common utilities.
"""
from apps.orders.services import get_cart_summary


def cart_context(request):
    """Add active session-cart information to template context."""
    summary = get_cart_summary(
        request.session.get("cart", {}),
        user=getattr(request, "user", None),
    )

    return {
        "cart_items": summary["items"],
        "cart_total": float(summary["total"]),
        "cart_count": sum(item["quantity"] for item in summary["items"]),
        "is_desktop": getattr(request, "is_desktop", True),
    }
