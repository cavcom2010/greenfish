from django.core.exceptions import ValidationError
from django.db.models import F

from apps.menu.models import MenuItem, StockMovement


def validate_cart_inventory(summary):
    """Reject unavailable or out-of-stock tracked items before order creation."""
    item_ids = [item.get("menu_item_id") for item in summary["items"] if item.get("menu_item_id")]
    if not item_ids:
        return

    menu_items = MenuItem.objects.in_bulk(item_ids)
    for item in summary["items"]:
        menu_item_id = item.get("menu_item_id")
        if not menu_item_id:
            continue
        menu_item = menu_items.get(int(menu_item_id))
        if not menu_item or not menu_item.is_available:
            raise ValidationError(f"{item['name']} is no longer available.")
        if menu_item.track_stock and menu_item.stock_quantity < item["quantity"]:
            raise ValidationError(f"Only {menu_item.stock_quantity} x {menu_item.name} is available.")


def reserve_order_stock(order):
    """Reserve tracked stock for an order while payment is pending."""
    tracked_items = [
        item for item in order.items.select_related("menu_item") if item.menu_item_id and item.menu_item.track_stock
    ]
    if not tracked_items:
        return

    locked = {
        item.pk: item
        for item in MenuItem.objects.select_for_update().filter(
            pk__in=[order_item.menu_item_id for order_item in tracked_items]
        )
    }
    for order_item in tracked_items:
        menu_item = locked[order_item.menu_item_id]
        if not menu_item.is_available:
            raise ValidationError(f"{menu_item.name} is no longer available.")
        if menu_item.stock_quantity < order_item.quantity:
            raise ValidationError(f"Only {menu_item.stock_quantity} x {menu_item.name} is available.")
        MenuItem.objects.filter(pk=menu_item.pk).update(stock_quantity=F("stock_quantity") - order_item.quantity)
        StockMovement.objects.create(
            menu_item=menu_item,
            order=order,
            movement_type=StockMovement.MovementType.RESERVED,
            quantity=-order_item.quantity,
            note=f"Reserved for {order.order_number}",
        )


def consume_order_stock(order):
    """Mark previously reserved stock as consumed after payment succeeds."""
    for movement in order.stock_movements.filter(movement_type=StockMovement.MovementType.RESERVED):
        if not order.stock_movements.filter(
            menu_item=movement.menu_item,
            movement_type=StockMovement.MovementType.CONSUMED,
        ).exists():
            StockMovement.objects.create(
                menu_item=movement.menu_item,
                order=order,
                movement_type=StockMovement.MovementType.CONSUMED,
                quantity=0,
                note=f"Consumed for {order.order_number}",
            )


def release_order_stock(order):
    """Release reserved stock for unpaid/failed/cancelled orders."""
    released_item_ids = set(
        order.stock_movements.filter(movement_type=StockMovement.MovementType.RELEASED).values_list("menu_item_id", flat=True)
    )
    for movement in order.stock_movements.filter(movement_type=StockMovement.MovementType.RESERVED):
        if movement.menu_item_id in released_item_ids:
            continue
        MenuItem.objects.filter(pk=movement.menu_item_id).update(stock_quantity=F("stock_quantity") + abs(movement.quantity))
        StockMovement.objects.create(
            menu_item=movement.menu_item,
            order=order,
            movement_type=StockMovement.MovementType.RELEASED,
            quantity=abs(movement.quantity),
            note=f"Released for {order.order_number}",
        )
