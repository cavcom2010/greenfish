from decimal import Decimal

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.core.models import NotificationEvent
from apps.core.test_support import create_order, create_user, ensure_site_settings
from apps.operations.permissions import (
    OPERATIONS_CASHIER_GROUP,
    OPERATIONS_KITCHEN_GROUP,
    OPERATIONS_MANAGER_GROUP,
)
from apps.orders.models import Order
from apps.payments.models import ManualPaymentReceipt, Payment, PaymentLog


class OperationsBoardTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.manager_user = self._create_ops_user("ops-manager@example.com", OPERATIONS_MANAGER_GROUP)
        self.cashier_user = self._create_ops_user("ops-cashier@example.com", OPERATIONS_CASHIER_GROUP)
        self.kitchen_user = self._create_ops_user("ops-kitchen@example.com", OPERATIONS_KITCHEN_GROUP)
        self.ungrouped_staff_user = create_user(email="ops-staff@example.com", is_staff=True)
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

        self.client.force_login(self.ungrouped_staff_user)
        for route in collection_routes + kitchen_routes:
            with self.subTest(route=route):
                self.assertIn(self.client.get(route).status_code, {302, 403})

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
        self.client.force_login(self.manager_user)

        response = self.client.post(
            reverse("orders:update_order_status", args=[order.id]),
            {"status": Order.OrderStatus.READY},
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.READY)
        self.assertIsNotNone(order.ready_at)

    def test_boards_only_show_paid_operational_orders(self):
        paid_order = create_order(
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.PAID,
        )
        unpaid_order = create_order(
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.PENDING,
            customer_name="Unpaid Customer",
        )

        self.client.force_login(self.kitchen_user)
        kitchen_response = self.client.get(reverse("operations:kanban_column", args=["confirmed"]))
        self.assertContains(kitchen_response, paid_order.order_number)
        self.assertNotContains(kitchen_response, unpaid_order.order_number)
        self.assertNotContains(kitchen_response, "Unpaid Customer")

        paid_ready = create_order(
            status=Order.OrderStatus.READY,
            payment_status=Order.PaymentStatus.PAID,
        )
        unpaid_ready = create_order(
            status=Order.OrderStatus.READY,
            payment_status=Order.PaymentStatus.PENDING,
            customer_name="Unpaid Ready",
        )
        self.client.force_login(self.cashier_user)
        collection_response = self.client.get(reverse("operations:collection_list_fragment"))
        self.assertContains(collection_response, paid_ready.order_number)
        self.assertNotContains(collection_response, unpaid_ready.order_number)
        self.assertNotContains(collection_response, "Unpaid Ready")

    def test_cashier_must_record_payment_evidence_before_marking_paid(self):
        order = create_order(
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PENDING,
            customer_name="Awaiting Payment",
        )
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_ops",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )

        self.client.force_login(self.kitchen_user)
        kitchen_response = self.client.get(reverse("operations:kanban_column", args=["confirmed"]))
        self.assertNotContains(kitchen_response, order.order_number)

        self.client.force_login(self.cashier_user)
        collection_response = self.client.get(reverse("operations:collection_list_fragment") + "?status=awaiting_payment")
        self.assertContains(collection_response, order.order_number)
        self.assertContains(collection_response, "Record Payment")

        missing_evidence = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_paid", "expected_status": Order.OrderStatus.PENDING},
        )
        self.assertEqual(missing_evidence.status_code, 400)
        self.assertIn("Select how the payment was taken", missing_evidence.json()["error"])

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {
                "action": "mark_paid",
                "expected_status": Order.OrderStatus.PENDING,
                "payment_method": ManualPaymentReceipt.Method.CARD_TERMINAL,
                "payment_amount_received": str(order.total_amount),
                "payment_reference_code": "AUTH123",
                "payment_notes": "Terminal receipt checked",
            },
            HTTP_USER_AGENT="Ops Tablet",
            REMOTE_ADDR="127.0.0.9",
        )
        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()
        payment = order.payment
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.external_payment_method, ManualPaymentReceipt.Method.CARD_TERMINAL)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.OrderStatus.CONFIRMED)
        receipt = payment.manual_receipt
        self.assertEqual(receipt.method, ManualPaymentReceipt.Method.CARD_TERMINAL)
        self.assertEqual(receipt.amount_due, order.total_amount)
        self.assertEqual(receipt.amount_received, order.total_amount)
        self.assertEqual(receipt.change_given, Decimal("0.00"))
        self.assertEqual(receipt.reference_code, "AUTH123")
        self.assertEqual(receipt.recorded_by, self.cashier_user)
        self.assertEqual(receipt.request_ip, "127.0.0.9")
        log = PaymentLog.objects.filter(payment=payment, event_type="offline_payment_marked_paid").latest("created_at")
        self.assertEqual(log.event_data["reference_code"], "AUTH123")
        self.assertEqual(log.event_data["actor_email"], self.cashier_user.email)

        self.client.force_login(self.kitchen_user)
        kitchen_response = self.client.get(reverse("operations:kanban_column", args=["confirmed"]))
        self.assertContains(kitchen_response, order.order_number)

    def test_cash_overpayment_records_change_given(self):
        order = create_order(status=Order.OrderStatus.PENDING, payment_status=Order.PaymentStatus.PENDING)
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_cash",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )
        self.client.force_login(self.cashier_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {
                "action": "mark_paid",
                "expected_status": Order.OrderStatus.PENDING,
                "payment_method": ManualPaymentReceipt.Method.CASH,
                "payment_amount_received": str(order.total_amount + Decimal("5.00")),
                "payment_reference_code": "TILL-1001",
            },
        )

        self.assertEqual(response.status_code, 200)
        receipt = ManualPaymentReceipt.objects.get(payment__order=order)
        self.assertEqual(receipt.change_given, Decimal("5.00"))

    def test_card_manual_payment_amount_must_match_order_total(self):
        order = create_order(status=Order.OrderStatus.PENDING, payment_status=Order.PaymentStatus.PENDING)
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_card_mismatch",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )
        self.client.force_login(self.cashier_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {
                "action": "mark_paid",
                "expected_status": Order.OrderStatus.PENDING,
                "payment_method": ManualPaymentReceipt.Method.PHONE_CARD,
                "payment_amount_received": str(order.total_amount + Decimal("1.00")),
                "payment_reference_code": "PHONEAUTH",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must match the order total exactly", response.json()["error"])
        self.assertFalse(ManualPaymentReceipt.objects.filter(payment__order=order).exists())

    def test_full_card_number_is_rejected_in_manual_payment_evidence(self):
        order = create_order(status=Order.OrderStatus.PENDING, payment_status=Order.PaymentStatus.PENDING)
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_pan",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )
        self.client.force_login(self.cashier_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {
                "action": "mark_paid",
                "expected_status": Order.OrderStatus.PENDING,
                "payment_method": ManualPaymentReceipt.Method.CARD_TERMINAL,
                "payment_amount_received": str(order.total_amount),
                "payment_reference_code": "4111 1111 1111 1111",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Do not store full card numbers", response.json()["error"])

    def test_stale_expected_status_is_rejected(self):
        order = create_order(status=Order.OrderStatus.PREPARING, payment_status=Order.PaymentStatus.PAID)
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_ready", "expected_status": Order.OrderStatus.CONFIRMED},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "Order changed. Refresh the board and try again.")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PREPARING)

    def test_unpaid_orders_cannot_be_actioned_directly(self):
        order = create_order(status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PENDING)
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "start_preparing", "expected_status": Order.OrderStatus.CONFIRMED},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "Only paid orders can be prepared on the operations boards.",
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CONFIRMED)

    def test_ready_action_enqueues_notification_without_blocking_status_change(self):
        order = create_order(
            status=Order.OrderStatus.PREPARING,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.PICKUP,
            user=self.user,
        )
        self.client.force_login(self.kitchen_user)

        response = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_ready"},
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.READY)
        self.assertTrue(
            NotificationEvent.objects.filter(
                order=order,
                channel=NotificationEvent.Channel.PUSH,
                event_type="order_ready",
                status=NotificationEvent.Status.PENDING,
            ).exists()
        )
