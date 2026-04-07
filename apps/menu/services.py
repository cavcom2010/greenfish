"""
Menu services - Recommendations and business logic.
"""
from django.db.models import Count, Q

from apps.orders.models import Order, OrderItem

from .models import MenuItem


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
