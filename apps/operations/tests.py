from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_order, create_user, ensure_site_settings
from apps.operations.permissions import (
    OPERATIONS_CASHIER_GROUP,
    OPERATIONS_KITCHEN_GROUP,
    OPERATIONS_MANAGER_GROUP,
)
from apps.orders.models import Order


class OperationsBoardTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.manager_user = self._create_ops_user("ops-manager@example.com", OPERATIONS_MANAGER_GROUP)
        self.cashier_user = self._create_ops_user("ops-cashier@example.com", OPERATIONS_CASHIER_GROUP)
        self.kitchen_user = self._create_ops_user("ops-kitchen@example.com", OPERATIONS_KITCHEN_GROUP)
        self.staff_fallback_user = create_user(email="ops-staff@example.com", is_staff=True)
        self.user = create_user(email="ops-user@example.com")

    def _create_ops_user(self, email, group_name):
        user = create_user(email=email, is_staff=True)
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)
        return user

    def test_operations_routes_require_the_correct_board_role(self):
        collection_routes = [
            reverse("operations:collection_board"),
            reverse("operations:collection_list_fragment"),
            reverse("operations:order_board"),
            reverse("operations:order_list_fragment"),
        ]
        kitchen_routes = [
            reverse("operations:kitchen_board"),
            reverse("operations:kanban_board"),
            reverse("operations:kanban_column", args=["confirmed"]),
        ]

        for route in collection_routes + kitchen_routes:
            with self.subTest(route=route):
                self.assertIn(self.client.get(route).status_code, {302, 403})

        self.client.force_login(self.cashier_user)
        for route in collection_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)
        for route in kitchen_routes:
            with self.subTest(route=route):
                self.assertIn(self.client.get(route).status_code, {302, 403})

        self.client.force_login(self.kitchen_user)
        for route in kitchen_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)
        for route in collection_routes:
            with self.subTest(route=route):
                self.assertIn(self.client.get(route).status_code, {302, 403})

        self.client.force_login(self.manager_user)
        for route in collection_routes + kitchen_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

        self.client.force_login(self.staff_fallback_user)
        for route in collection_routes + kitchen_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_kitchen_user_can_progress_order_to_ready_but_not_dispatch(self):
        order = create_order(
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.DELIVERY,
            delivery_address_line1="12 Test Street",
            delivery_city="Leeds",
            delivery_postcode="LS1 1AA",
        )
        self.client.force_login(self.kitchen_user)

        start = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "start_preparing"},
        )
        self.assertEqual(start.status_code, 200)

        mark_ready = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_ready"},
        )
        self.assertEqual(mark_ready.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.READY)
        self.assertIsNotNone(order.ready_at)
        self.assertIsNone(order.dispatched_at)

        dispatch = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_dispatched"},
        )
        self.assertEqual(dispatch.status_code, 400)

    def test_cashier_can_dispatch_and_complete_delivery_orders(self):
        order = create_order(
            status=Order.OrderStatus.READY,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.DELIVERY,
            delivery_address_line1="12 Test Street",
            delivery_city="Leeds",
            delivery_postcode="LS1 1AA",
        )
        self.client.force_login(self.cashier_user)

        dispatch = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_dispatched", "handover_notes": "Driver collected order"},
        )
        self.assertEqual(dispatch.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.OUT_FOR_DELIVERY)
        self.assertIsNotNone(order.dispatched_at)
        self.assertEqual(order.handover_notes, "Driver collected order")

        delivered = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_delivered"},
        )
        self.assertEqual(delivered.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.delivered_at)
        self.assertIsNotNone(order.completed_at)

    def test_cashier_can_complete_pickup_handover(self):
        order = create_order(status=Order.OrderStatus.READY, payment_status=Order.PaymentStatus.PAID)
        self.client.force_login(self.cashier_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_collected", "handover_notes": "Collected by customer"},
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.collected_at)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.completed_by, self.cashier_user)
        self.assertEqual(order.handover_notes, "Collected by customer")

    def test_manager_can_cancel_with_reason(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "cancel_order", "cancel_reason": "Customer requested cancellation"},
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertEqual(order.cancel_reason, "Customer requested cancellation")
        self.assertEqual(order.cancelled_by, self.manager_user)

    def test_operations_detail_can_save_notes_without_state_change(self):
        order = create_order(status=Order.OrderStatus.PREPARING, payment_status=Order.PaymentStatus.PAID)
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {
                "action": "save_notes",
                "staff_notes": "No peanuts",
                "handover_notes": "Double-check allergy label",
            },
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PREPARING)
        self.assertEqual(order.staff_notes, "No peanuts")
        self.assertEqual(order.handover_notes, "Double-check allergy label")

    def test_legacy_orders_update_route_still_works_through_operations_service(self):
        order = create_order(status=Order.OrderStatus.PREPARING, payment_status=Order.PaymentStatus.PAID)
        self.client.force_login(self.staff_fallback_user)

        response = self.client.post(
            reverse("orders:update_order_status", args=[order.id]),
            {"status": Order.OrderStatus.READY},
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.READY)
        self.assertIsNotNone(order.ready_at)
