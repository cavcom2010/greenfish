from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.test_support import create_menu_item, create_order
from apps.menu.models import StockMovement
from apps.orders.delivery import apply_delivery_pricing
from apps.orders.fulfilment import reserve_fulfilment_slot
from apps.orders.inventory import release_order_stock, reserve_order_stock
from apps.orders.models import DeliveryZone, FulfilmentCapacityRule, FulfilmentSlotReservation, Order


class BackendUpgradeOrderTests(TestCase):
    def test_inventory_reserve_and_release_updates_stock_ledger(self):
        item = create_menu_item(track_stock=True, stock_quantity=3)
        order = create_order()
        order.items.update(menu_item=item, quantity=2, item_price=item.price)

        reserve_order_stock(order)
        item.refresh_from_db()
        self.assertEqual(item.stock_quantity, 1)
        self.assertTrue(order.stock_movements.filter(movement_type=StockMovement.MovementType.RESERVED).exists())

        release_order_stock(order)
        item.refresh_from_db()
        self.assertEqual(item.stock_quantity, 3)
        self.assertTrue(order.stock_movements.filter(movement_type=StockMovement.MovementType.RELEASED).exists())

    def test_inventory_reservation_blocks_oversell(self):
        item = create_menu_item(track_stock=True, stock_quantity=1)
        order = create_order()
        order.items.update(menu_item=item, quantity=2, item_price=item.price)

        with self.assertRaises(ValidationError):
            reserve_order_stock(order)

    def test_fulfilment_capacity_reservation_blocks_full_slot(self):
        slot = timezone.localtime(timezone.now() + timezone.timedelta(hours=2)).replace(second=0, microsecond=0)
        FulfilmentCapacityRule.objects.create(
            service_type=Order.ServiceType.PICKUP,
            day_of_week=slot.weekday(),
            start_time=(slot - timezone.timedelta(minutes=30)).time(),
            end_time=(slot + timezone.timedelta(minutes=30)).time(),
            max_orders=1,
            lead_time_minutes=1,
        )
        first = create_order(service_type=Order.ServiceType.PICKUP, fulfilment_slot_start=slot)
        reserve_fulfilment_slot(first)

        second = create_order(service_type=Order.ServiceType.PICKUP, fulfilment_slot_start=slot)
        with self.assertRaises(ValidationError):
            reserve_fulfilment_slot(second)

        self.assertEqual(FulfilmentSlotReservation.objects.count(), 1)

    @override_settings(GOOGLE_ROUTES_API_ENABLED=False)
    def test_delivery_pricing_applies_zone_fee_and_eta(self):
        DeliveryZone.objects.create(
            name="Inner",
            min_distance_miles=Decimal("0.00"),
            max_distance_miles=Decimal("3.00"),
            fee=Decimal("2.50"),
            estimated_minutes=25,
        )
        order = create_order(
            service_type=Order.ServiceType.DELIVERY,
            delivery_distance_miles=Decimal("2.20"),
            subtotal=Decimal("20.00"),
            discount_amount=Decimal("1.00"),
            total_amount=Decimal("19.00"),
        )

        apply_delivery_pricing(order)
        order.refresh_from_db()
        self.assertEqual(order.delivery_fee, Decimal("2.50"))
        self.assertEqual(order.delivery_zone_name, "Inner")
        self.assertEqual(order.delivery_eta_minutes, 25)
        self.assertEqual(order.total_amount, Decimal("21.50"))
