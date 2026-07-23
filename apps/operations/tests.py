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


class DriverPermissionsTests(TestCase):
    """The driver role must unlock only the driver surface — never the
    back-office boards, order_action, or order detail."""

    def setUp(self):
        ensure_site_settings()
        from apps.operations.permissions import OPERATIONS_DRIVER_GROUP

        self.driver_user = create_user(email="driver@example.com", is_staff=True)
        group, _ = Group.objects.get_or_create(name=OPERATIONS_DRIVER_GROUP)
        self.driver_user.groups.add(group)

        self.cashier_user = create_user(email="cashier2@example.com", is_staff=True)
        cashier_group, _ = Group.objects.get_or_create(name=OPERATIONS_CASHIER_GROUP)
        self.cashier_user.groups.add(cashier_group)

        self.manager_user = create_user(email="manager2@example.com", is_staff=True)
        manager_group, _ = Group.objects.get_or_create(name=OPERATIONS_MANAGER_GROUP)
        self.manager_user.groups.add(manager_group)

    def _delivery_order_in_dispatched_run(self, driver_user=None):
        from apps.orders.models import DeliveryDriver, DeliveryRun, DeliveryRunOrder

        order = create_order(
            status=Order.OrderStatus.OUT_FOR_DELIVERY,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.DELIVERY,
            delivery_address_line1="12 Test Street",
            delivery_city="Leeds",
            delivery_postcode="LS1 1AA",
        )
        driver = DeliveryDriver.objects.create(name="Test Driver", user=driver_user)
        run = DeliveryRun.objects.create(driver=driver, status=DeliveryRun.Status.DISPATCHED)
        DeliveryRunOrder.objects.create(run=run, order=order, sequence=1)
        return order

    def test_driver_is_not_operations_staff(self):
        from apps.operations.permissions import is_delivery_driver, is_operations_staff

        self.assertFalse(is_operations_staff(self.driver_user))
        self.assertTrue(is_delivery_driver(self.driver_user))
        self.assertTrue(is_operations_staff(self.cashier_user))

    def test_driver_cannot_access_back_office_routes(self):
        order = self._delivery_order_in_dispatched_run(driver_user=self.driver_user)
        self.client.force_login(self.driver_user)

        blocked_gets = [
            reverse("operations:collection_board"),
            reverse("operations:kitchen_board"),
            reverse("operations:order_detail_modal", args=[order.id]),
        ]
        for route in blocked_gets:
            with self.subTest(route=route):
                self.assertIn(self.client.get(route).status_code, {302, 403})

        action = self.client.post(
            reverse("operations:order_action", args=[order.id]),
            {"action": "mark_delivered"},
        )
        self.assertEqual(action.status_code, 403)

    def test_board_access_matrix(self):
        from apps.operations.permissions import BOARD_DRIVER, can_access_board

        self.assertTrue(can_access_board(self.driver_user, BOARD_DRIVER))
        self.assertFalse(can_access_board(self.cashier_user, BOARD_DRIVER))
        self.assertTrue(can_access_board(self.manager_user, BOARD_DRIVER))

    def test_driver_mark_delivered_requires_ownership(self):
        from apps.operations.permissions import can_perform_action

        own_order = self._delivery_order_in_dispatched_run(driver_user=self.driver_user)
        foreign_order = self._delivery_order_in_dispatched_run(driver_user=None)

        self.assertTrue(can_perform_action(self.driver_user, "mark_delivered", order=own_order))
        self.assertFalse(can_perform_action(self.driver_user, "mark_delivered", order=foreign_order))
        # Without an order there is no ownership proof — deny.
        self.assertFalse(can_perform_action(self.driver_user, "mark_delivered"))
        # Other actions stay denied even on own orders.
        self.assertFalse(can_perform_action(self.driver_user, "mark_dispatched", order=own_order))


class DeliveryRunServiceTests(TestCase):
    """Assignment, dispatch, ETA, and run-completion orchestration."""

    def setUp(self):
        ensure_site_settings()
        from apps.orders.models import DeliveryDriver

        self.manager = create_user(email="run-manager@example.com", is_staff=True)
        group, _ = Group.objects.get_or_create(name=OPERATIONS_MANAGER_GROUP)
        self.manager.groups.add(group)
        self.driver = DeliveryDriver.objects.create(name="Runner")

    def _delivery_order(self, **overrides):
        defaults = dict(
            status=Order.OrderStatus.READY,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.DELIVERY,
            delivery_address_line1="12 Test Street",
            delivery_city="Leeds",
            delivery_postcode="LS1 1AA",
            delivery_eta_minutes=25,
        )
        defaults.update(overrides)
        return create_order(**defaults)

    def test_assign_creates_single_draft_run_per_driver(self):
        from apps.operations import delivery_services as ds
        from apps.orders.models import DeliveryRun

        first = ds.assign_order_to_run(self._delivery_order(), self.driver)
        second = ds.assign_order_to_run(self._delivery_order(), self.driver)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(
            DeliveryRun.objects.filter(driver=self.driver, status=DeliveryRun.Status.DRAFT).count(), 1
        )
        first.order.refresh_from_db()
        self.assertEqual(first.order.delivery_driver, self.driver)

    def test_assign_rejects_unpaid_and_pickup_orders(self):
        from apps.operations import delivery_services as ds

        unpaid = self._delivery_order(payment_status=Order.PaymentStatus.PENDING)
        with self.assertRaises(ValueError):
            ds.assign_order_to_run(unpaid, self.driver)

        pickup = create_order(
            status=Order.OrderStatus.READY,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.PICKUP,
        )
        with self.assertRaises(ValueError):
            ds.assign_order_to_run(pickup, self.driver)

    def test_unassign_resequences_and_deletes_empty_run(self):
        from apps.operations import delivery_services as ds
        from apps.orders.models import DeliveryRun

        order_a = self._delivery_order()
        order_b = self._delivery_order()
        ds.assign_order_to_run(order_a, self.driver)
        run_order_b = ds.assign_order_to_run(order_b, self.driver)

        ds.unassign_order(order_a)
        run_order_b.refresh_from_db()
        self.assertEqual(run_order_b.sequence, 1)
        order_a.refresh_from_db()
        self.assertIsNone(order_a.delivery_driver)

        ds.unassign_order(order_b)
        self.assertFalse(DeliveryRun.objects.filter(driver=self.driver).exists())

    def test_dispatch_prunes_cancelled_orders_and_sets_etas(self):
        from apps.operations import delivery_services as ds

        keep = self._delivery_order()
        cancelled = self._delivery_order()
        ds.assign_order_to_run(keep, self.driver)
        run = ds.assign_order_to_run(cancelled, self.driver).run
        cancelled.update_status(Order.OrderStatus.CANCELLED, self.manager)

        ds.dispatch_run(run, self.manager)
        run.refresh_from_db()
        keep.refresh_from_db()

        self.assertEqual(run.status, run.Status.DISPATCHED)
        self.assertEqual(run.run_orders.count(), 1)
        self.assertEqual(keep.status, Order.OrderStatus.OUT_FOR_DELIVERY)
        run_order = run.run_orders.get()
        self.assertIsNotNone(run_order.eta_at)

    def test_dispatch_eta_increments_by_sequence(self):
        from apps.operations import delivery_services as ds

        first = self._delivery_order()
        second = self._delivery_order()
        ds.assign_order_to_run(first, self.driver)
        run = ds.assign_order_to_run(second, self.driver).run

        ds.dispatch_run(run, self.manager)
        stops = list(run.run_orders.order_by("sequence"))
        gap = (stops[1].eta_at - stops[0].eta_at).total_seconds() / 60
        self.assertEqual(round(gap), 7)  # DELIVERY_PER_STOP_MINUTES default

    def test_dispatch_enqueues_push_notifications(self):
        from apps.operations import delivery_services as ds

        customer = create_user(email="push-customer@example.com")
        order = self._delivery_order(user=customer)
        run = ds.assign_order_to_run(order, self.driver).run
        ds.dispatch_run(run, self.manager)

        self.assertTrue(
            NotificationEvent.objects.filter(
                order=order,
                channel=NotificationEvent.Channel.PUSH,
                event_type="order_out_for_delivery",
                status=NotificationEvent.Status.PENDING,
            ).exists()
        )

    def test_run_autocompletes_on_mixed_delivered_and_cancelled(self):
        from apps.operations import delivery_services as ds

        delivered = self._delivery_order()
        cancelled_later = self._delivery_order()
        ds.assign_order_to_run(delivered, self.driver)
        run = ds.assign_order_to_run(cancelled_later, self.driver).run
        ds.dispatch_run(run, self.manager)

        from apps.operations.services import ACTION_CANCEL_ORDER, perform_order_action

        perform_order_action(
            cancelled_later, ACTION_CANCEL_ORDER, self.manager, cancel_reason="No answer"
        )
        run.refresh_from_db()
        self.assertEqual(run.status, run.Status.DISPATCHED)  # one stop still open

        delivered.refresh_from_db()  # dispatch updated status in the DB
        ds.driver_mark_delivered(delivered, self.manager)
        run.refresh_from_db()
        self.assertEqual(run.status, run.Status.COMPLETED)
        self.assertIsNotNone(run.completed_at)

        run_order = run.run_orders.get(order=delivered)
        self.assertIsNotNone(run_order.delivered_at)

    def test_cancel_unassigns_from_draft_run(self):
        from apps.operations import delivery_services as ds
        from apps.orders.models import DeliveryRun

        order = self._delivery_order()
        ds.assign_order_to_run(order, self.driver)

        from apps.operations.services import ACTION_CANCEL_ORDER, perform_order_action

        perform_order_action(order, ACTION_CANCEL_ORDER, self.manager, cancel_reason="Test")
        order.refresh_from_db()
        self.assertIsNone(order.delivery_driver)
        self.assertFalse(DeliveryRun.objects.filter(driver=self.driver).exists())
