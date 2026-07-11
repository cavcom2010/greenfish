"""
Menu services - Recommendations and business logic.
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

from apps.orders.models import Order, OrderItem

from .models import MenuItem

logger = logging.getLogger(__name__)

POPULAR_ITEMS_CACHE_SECONDS = 60 * 60


def get_popular_menu_items(limit=6, days=14):
    """Return the current best sellers, most-ordered first.

    Ranks available menu items by the number of distinct paid,
    non-cancelled orders containing them in the last ``days`` days, so one
    50-portion catering order counts the same as one regular order.
    Meal-deal purchases count toward their selected component items: deal
    lines are stored with ``menu_item`` NULL and each modifier's ``id`` is
    the component menu item chosen in the builder. When there isn't enough
    recent order history to fill ``limit`` slots, tops up with items the
    admin has flagged ``is_popular``.

    The sales ranking (ids only) is cached for an hour; availability is
    re-checked on every call so 86'd items drop out immediately.
    """
    cache_key = f"menu:popular-item-ids:v2:{limit}:{days}"
    # The production cache is Redis and Django's backend raises on
    # connection errors — the homepage must not depend on Redis being up.
    try:
        ranked_ids = cache.get(cache_key)
    except Exception:
        logger.warning("Popular-items cache read failed; recomputing", exc_info=True)
        ranked_ids = None

    if ranked_ids is None:
        since = timezone.now() - timedelta(days=days)
        recent_lines = OrderItem.objects.filter(
            order__created_at__gte=since,
            order__payment_status=Order.PaymentStatus.PAID,
        ).exclude(order__status=Order.OrderStatus.CANCELLED)

        orders_by_item = defaultdict(set)

        # Direct menu-item lines.
        for item_id, order_id in recent_lines.filter(menu_item__isnull=False).values_list(
            "menu_item", "order_id"
        ):
            orders_by_item[item_id].add(order_id)

        # Meal-deal lines: attribute the order to each chosen component.
        # (Regular items' modifiers reference MenuItemModifier ids, but
        # those lines always have menu_item set, so they're never parsed.)
        for modifiers, order_id in recent_lines.filter(menu_item__isnull=True).values_list(
            "modifiers", "order_id"
        ):
            for modifier in modifiers or []:
                if not isinstance(modifier, dict):
                    continue
                try:
                    component_id = int(modifier.get("id"))
                except (TypeError, ValueError):
                    continue
                orders_by_item[component_id].add(order_id)

        ranked_ids = [
            item_id
            for item_id, order_ids in sorted(
                orders_by_item.items(), key=lambda pair: (-len(pair[1]), pair[0])
            )
        ][:limit]
        try:
            cache.set(cache_key, ranked_ids, POPULAR_ITEMS_CACHE_SECONDS)
        except Exception:
            logger.warning("Popular-items cache write failed", exc_info=True)

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
