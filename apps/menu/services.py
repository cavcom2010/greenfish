"""
Menu services - Recommendations and business logic.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.orders.models import Order, OrderItem

from .models import MenuItem

POPULAR_ITEMS_CACHE_SECONDS = 60 * 60


def get_popular_menu_items(limit=6, days=14):
    """Return the current best sellers, most-ordered first.

    Ranks available menu items by quantity sold across paid, non-cancelled
    orders in the last ``days`` days. When there isn't enough recent order
    history to fill ``limit`` slots (new shop, quiet fortnight), tops up
    with items the admin has flagged ``is_popular``.

    The sales ranking (ids only) is cached for an hour; availability is
    re-checked on every call so 86'd items drop out immediately.
    """
    cache_key = f"menu:popular-item-ids:{limit}:{days}"
    ranked_ids = cache.get(cache_key)
    if ranked_ids is None:
        since = timezone.now() - timedelta(days=days)
        ranked_ids = list(
            OrderItem.objects.filter(
                order__created_at__gte=since,
                order__payment_status=Order.PaymentStatus.PAID,
                menu_item__isnull=False,
            )
            .exclude(order__status=Order.OrderStatus.CANCELLED)
            .values("menu_item")
            .annotate(total_quantity=Sum("quantity"))
            .order_by("-total_quantity", "menu_item")
            .values_list("menu_item", flat=True)[:limit]
        )
        cache.set(cache_key, ranked_ids, POPULAR_ITEMS_CACHE_SECONDS)

    items_by_id = (
        MenuItem.objects.filter(id__in=ranked_ids, is_available=True)
        .select_related("category")
        .in_bulk()
    )
    items = [items_by_id[item_id] for item_id in ranked_ids if item_id in items_by_id]

    if len(items) < limit:
        flagged = (
            MenuItem.objects.filter(is_available=True, is_popular=True)
            .exclude(id__in=[item.id for item in items])
            .select_related("category")
            .order_by("category__sort_order", "sort_order")[: limit - len(items)]
        )
        items.extend(flagged)

    return items


def get_recommendations(item_id, limit=4):
    """
    Get "Customers also ordered" recommendations.
    
    Finds items that are frequently ordered together with the given item.
    Uses simple co-occurrence counting (items appearing in same orders).
    
    Args:
        item_id: The menu item ID to get recommendations for
        limit: Maximum number of recommendations to return
    
    Returns:
        QuerySet of recommended MenuItem objects
    """
    # Find orders containing this item
    orders_with_item = Order.objects.filter(
        items__menu_item_id=item_id
    ).values_list('id', flat=True)
    
    if not orders_with_item:
        # No orders yet, return popular items instead
        return MenuItem.objects.filter(
            is_available=True,
            is_popular=True
        ).exclude(id=item_id)[:limit]
    
    # Find other items frequently ordered in same orders
    related_items = OrderItem.objects.filter(
        order_id__in=orders_with_item
    ).exclude(
        menu_item_id=item_id
    ).values('menu_item').annotate(
        frequency=Count('id')
    ).order_by('-frequency')[:limit]
    
    # Get the actual MenuItem objects
    item_ids = [item['menu_item'] for item in related_items if item['menu_item']]
    
    if not item_ids:
        # No related items found, return popular items
        return MenuItem.objects.filter(
            is_available=True,
            is_popular=True
        ).exclude(id=item_id)[:limit]
    
    # Preserve order of frequency
    from django.db.models import Case, When
    preserved_order = Case(*[When(id=id, then=pos) for pos, id in enumerate(item_ids)])
    
    return MenuItem.objects.filter(
        id__in=item_ids,
        is_available=True
    ).order_by(preserved_order)


def get_popular_combinations(limit=3):
    """
    Get popular meal combinations.
    
    Returns pairs of items that are frequently ordered together.
    """
    from django.db.models import F
    
    # Get orders with multiple items
    multi_item_orders = Order.objects.annotate(
        item_count=Count('items')
    ).filter(item_count__gte=2).values_list('id', flat=True)[:100]
    
    # Find common pairs (simplified approach)
    # In production, you might want to use more sophisticated ML
    popular_items = MenuItem.objects.filter(
        is_available=True,
        order_items__order_id__in=multi_item_orders
    ).annotate(
        order_count=Count('order_items')
    ).order_by('-order_count')[:limit * 2]
    
    return popular_items
