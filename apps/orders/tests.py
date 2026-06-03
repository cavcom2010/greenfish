from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.context_processors import cart_context
from apps.core.test_support import (
    create_meal_deal,
    create_menu_item,
    create_offer,
    create_order,
    create_user,
    create_voucher,
    ensure_site_settings,
)
from apps.offers.models import Offer, VoucherUsage
from apps.operations.permissions import OPERATIONS_MANAGER_GROUP
from apps.orders.models import Order, OrderItem
from apps.orders.services import (
    delivery_map_settings,
    get_cart_summary,
    haversine_miles,
    validate_service_details,
)
from apps.payments.models import Payment


class OrderFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_site_settings()
        self.user = create_user()
        self.staff_user = create_user(email="staff@example.com", is_staff=True)
        self.menu_item = create_menu_item()
        self.offer = create_offer()
        self.voucher = create_voucher(offer=self.offer)
        self.deal = create_meal_deal(self.menu_item)

    def test_add_update_remove_cart_item_and_context_processor(self):
        add_response = self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 2, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.json()["cart_count"], 2)
        self.assertEqual(add_response.json()["cart_total"], "25.00")
        cart = self.client.session["cart"]
        item_id = next(iter(cart.keys()))

        update_response = self.client.post(
            reverse("orders:update_cart_item", args=[item_id]),
            {"quantity": 3},
        )
        self.assertEqual(update_response.status_code, 302)

        factory = RequestFactory()
        request = factory.get("/")
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session = self.client.session
        context = cart_context(request)
        self.assertEqual(context["cart_count"], 3)

        remove_response = self.client.post(reverse("orders:remove_from_cart", args=[item_id]))
        self.assertEqual(remove_response.status_code, 302)
        self.assertEqual(self.client.session.get("cart"), {})

    def test_ajax_cart_updates_return_count_and_total(self):
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        item_id = next(iter(self.client.session["cart"].keys()))

        update_response = self.client.post(
            reverse("orders:update_cart_item", args=[item_id]),
            {"quantity": 3},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["cart_count"], 3)
        self.assertEqual(update_response.json()["cart_total"], "37.50")

    def test_htmx_remove_from_cart_refreshes_drawer_and_triggers_cart_state(self):
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        item_id = next(iter(self.client.session["cart"].keys()))

        remove_response = self.client.post(
            reverse("orders:remove_from_cart", args=[item_id]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(remove_response.status_code, 200)
        self.assertContains(remove_response, "Your basket is empty")
        self.assertIn("cart-updated", remove_response.headers["HX-Trigger"])
        self.assertIn('"cart_count": 0', remove_response.headers["HX-Trigger"])

    def test_ajax_remove_from_cart_returns_count_and_total(self):
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        item_id = next(iter(self.client.session["cart"].keys()))

        remove_response = self.client.post(
            reverse("orders:remove_from_cart", args=[item_id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(remove_response.json()["cart_count"], 0)
        self.assertEqual(remove_response.json()["cart_total"], "0.00")

    def test_meal_deal_can_be_added_to_cart(self):
        deal_item = self.deal.items.first()
        option = deal_item.options.first()
        response = self.client.post(
            reverse("orders:add_to_cart"),
            {"deal_id": self.deal.pk, "quantity": 1, f"item_{deal_item.id}": option.menu_item_id},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        cart = self.client.session["cart"]
        self.assertEqual(len(cart), 1)
        stored_item = next(iter(cart.values()))
        self.assertEqual(stored_item["name"], self.deal.name)

    def test_checkout_and_voucher_flow(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        voucher_response = self.client.post(reverse("orders:apply_voucher"), {"code": self.voucher.code})
        self.assertEqual(voucher_response.status_code, 302)

        checkout_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(checkout_response.status_code, 200)
        self.assertContains(checkout_response, self.voucher.code)

    def test_apply_voucher_endpoint_is_rate_limited_per_session(self):
        with patch(
            "apps.orders.views.VOUCHER_ATTEMPT_LIMITS",
            (("session", 2, 600), ("ip", 99, 600)),
        ):
            for _ in range(2):
                response = self.client.post(
                    reverse("orders:apply_voucher"),
                    {"code": "NOPE"},
                    HTTP_ACCEPT="application/json",
                )
                self.assertEqual(response.status_code, 400)

            blocked = self.client.post(
                reverse("orders:apply_voucher"),
                {"code": "NOPE"},
                HTTP_ACCEPT="application/json",
            )

        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        self.assertIn("Too many voucher attempts", blocked.json()["error"])

    def test_apply_voucher_endpoint_is_rate_limited_per_ip_across_sessions(self):
        other_client = self.client_class()

        with patch(
            "apps.orders.views.VOUCHER_ATTEMPT_LIMITS",
            (("session", 99, 600), ("ip", 2, 600)),
        ):
            for client in (self.client, other_client):
                response = client.post(
                    reverse("orders:apply_voucher"),
                    {"code": "NOPE"},
                    HTTP_ACCEPT="application/json",
                    REMOTE_ADDR="198.51.100.10",
                )
                self.assertEqual(response.status_code, 400)

            blocked = self.client.post(
                reverse("orders:apply_voucher"),
                {"code": "NOPE"},
                HTTP_ACCEPT="application/json",
                REMOTE_ADDR="198.51.100.10",
            )

        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        self.assertIn("Too many voucher attempts", blocked.json()["error"])

    def test_offer_can_be_activated_and_applies_automatically(self):
        offer = create_offer(
            name="Burger Deal",
            value=Decimal("2.00"),
            offer_type=Offer.OfferType.FIXED,
        )
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )

        activate_response = self.client.post(
            reverse("offers:activate", args=[offer.pk]),
            {"next": reverse("menu:menu")},
        )
        self.assertEqual(activate_response.status_code, 302)
        self.assertEqual(self.client.session["active_offer_id"], offer.pk)

        checkout_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(checkout_response.context["discount"], Decimal("2.00"))
        self.assertEqual(checkout_response.context["active_offer"], offer)

    def test_offer_activation_scopes_discount_to_eligible_items(self):
        offer = create_offer(
            name="Mains Half Price",
            value=Decimal("50.00"),
            offer_type=Offer.OfferType.PERCENTAGE,
        )
        offer.applicable_items.add(self.menu_item)
        second_item = create_menu_item(name="Drink", price=Decimal("6.00"))

        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": second_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        self.client.post(
            reverse("offers:activate", args=[offer.pk]),
            {"next": reverse("menu:menu")},
        )

        checkout_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(checkout_response.context["discount"], Decimal("6.25"))
        self.assertEqual(checkout_response.context["total"], Decimal("12.25"))

    def test_voucher_respects_minimum_order_amount(self):
        limited_offer = create_offer(
            name="Big Order Only",
            value=Decimal("5.00"),
            offer_type=Offer.OfferType.FIXED,
        )
        limited_offer.minimum_order_amount = Decimal("20.00")
        limited_offer.save(update_fields=["minimum_order_amount"])
        voucher = create_voucher(code="BIG20", offer=limited_offer)

        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        summary = get_cart_summary(
            self.client.session.get("cart", {}),
            user=self.user,
            voucher_code=voucher.code,
        )

        self.assertIsNone(summary["voucher"])
        self.assertEqual(
            summary["voucher_error"],
            "Spend at least GBP 20.00 to use Big Order Only.",
        )

    def test_pay_instore_does_not_process_vouchers_or_create_orders(self):
        limited_offer = create_offer(
            name="Guest Once",
            value=Decimal("3.00"),
            offer_type=Offer.OfferType.FIXED,
        )
        voucher = create_voucher(code="GUEST1", offer=limited_offer)
        voucher.max_uses_per_customer = 1
        voucher.save(update_fields=["max_uses_per_customer"])
        create_order(
            customer_phone="07747055935",
            voucher_code=voucher.code,
            applied_offer=limited_offer,
            discount_amount=Decimal("3.00"),
            total_amount=Decimal("9.50"),
        )

        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        session = self.client.session
        session["voucher_code"] = voucher.code
        session.save()

        response = self.client.post(
            reverse("orders:pay_instore"),
            {
                "customer_name": "Guest Customer",
                "customer_phone": "07747 055935",
                "customer_email": "guest@example.com",
                "pickup_time": "15",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:checkout"))
        self.assertEqual(Order.objects.filter(voucher_code=voucher.code).count(), 1)
        self.assertEqual(self.client.session.get("voucher_code"), voucher.code)

    def test_service_type_endpoint_persists_delivery_choice(self):
        response = self.client.post(
            reverse("orders:set_service_type"),
            {"service_type": Order.ServiceType.DELIVERY},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["service_type"], Order.ServiceType.DELIVERY)

    @override_settings(DELIVERY_ENABLED=False)
    def test_delivery_env_switch_forces_pickup(self):
        response = self.client.post(
            reverse("orders:set_service_type"),
            {"service_type": Order.ServiceType.DELIVERY},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service_type"], Order.ServiceType.PICKUP)
        self.assertTrue(response.json()["delivery_coerced"])
        self.assertEqual(self.client.session["service_type"], Order.ServiceType.PICKUP)

        checkout_session = self.client.session
        checkout_session["service_type"] = Order.ServiceType.DELIVERY
        checkout_session.save()
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        checkout_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(checkout_response.status_code, 200)
        self.assertEqual(checkout_response.context["service_type"], Order.ServiceType.PICKUP)
        self.assertFalse(checkout_response.context["delivery_enabled"])
        self.assertNotContains(checkout_response, 'data-service="delivery"')
        self.assertNotContains(checkout_response, "Delivery Address")
        self.assertNotContains(checkout_response, "Delivered to your address")
        self.assertNotContains(checkout_response, "Delivery Time")

        self.client.cookies["view_mode"] = "desktop"
        checkout_session = self.client.session
        checkout_session["service_type"] = Order.ServiceType.DELIVERY
        checkout_session.save()
        desktop_checkout_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(desktop_checkout_response.status_code, 200)
        self.assertEqual(desktop_checkout_response.context["service_type"], Order.ServiceType.PICKUP)
        self.assertNotContains(desktop_checkout_response, 'data-desktop-service="delivery"')
        self.assertNotContains(desktop_checkout_response, "Delivery Address")
        self.assertNotContains(desktop_checkout_response, "Delivered to your address")
        self.assertNotContains(desktop_checkout_response, "Delivery Time")

    @override_settings(DELIVERY_ENABLED=False)
    def test_delivery_env_switch_hides_public_home_delivery_copy(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["delivery_enabled"])
        self.assertNotContains(response, 'data-service="delivery"')
        self.assertNotContains(response, '>Delivery</button>')

        self.client.cookies["view_mode"] = "desktop"
        desktop_response = self.client.get(reverse("core:home"))
        self.assertEqual(desktop_response.status_code, 200)
        self.assertFalse(desktop_response.context["delivery_enabled"])
        self.assertNotContains(desktop_response, 'data-desktop-service="delivery"')
        self.assertNotContains(desktop_response, "delivered fresh to your door")
        self.assertNotContains(desktop_response, "Fast delivery")

    def test_delivery_admin_switch_forces_pickup(self):
        ensure_site_settings(delivery_enabled=False)
        response = self.client.post(
            reverse("orders:set_service_type"),
            {"service_type": Order.ServiceType.DELIVERY},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service_type"], Order.ServiceType.PICKUP)
        self.assertFalse(response.json()["delivery_enabled"])

    def test_haversine_miles_calculates_expected_distance(self):
        distance = haversine_miles("53.800755", "-1.549077", "53.796500", "-1.541800")
        self.assertIsNotNone(distance)
        self.assertGreater(distance, 0.40)
        self.assertLess(distance, 0.50)

    @override_settings(
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        GOOGLE_MAPS_MAP_ID="test-map-id",
        SHOP_LATITUDE="",
        SHOP_LONGITUDE="",
        DELIVERY_RADIUS_MILES=3,
    )
    def test_delivery_map_settings_require_key_and_shop_coordinates(self):
        settings_obj = ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            shop_latitude=Decimal("53.800755"),
            shop_longitude=Decimal("-1.549077"),
            delivery_radius_miles=Decimal("3.00"),
        )

        config = delivery_map_settings()

        self.assertTrue(settings_obj.is_delivery_map_configured)
        self.assertTrue(config["configured"])
        self.assertEqual(config["api_key"], "test-google-key")
        self.assertEqual(config["map_id"], "test-map-id")
        self.assertEqual(config["radius_miles"], Decimal("3.00"))

    def test_checkout_uses_polished_manual_delivery_panel_when_map_unconfigured(self):
        ensure_site_settings(delivery_enabled=True, delivery_map_enabled=True)
        self.client.post(
            reverse("orders:add_to_cart"),
            {
                "menu_item_id": self.menu_item.pk,
                "quantity": 1,
                "modifiers": "[]",
                "service_type": Order.ServiceType.DELIVERY,
            },
            HTTP_ACCEPT="application/json",
        )

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live delivery check")
        self.assertContains(response, "delivery-precision-card")
        self.assertContains(response, "Live map verification is not configured yet")
        self.assertContains(response, "checkout-delivery-map.js")
        self.assertNotContains(response, "Map lookup is not configured yet")

    @override_settings(
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
    )
    def test_desktop_checkout_uses_live_delivery_map_panel_when_configured(self):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        self.client.post(
            reverse("orders:add_to_cart"),
            {
                "menu_item_id": self.menu_item.pk,
                "quantity": 1,
                "modifiers": "[]",
                "service_type": Order.ServiceType.DELIVERY,
            },
            HTTP_ACCEPT="application/json",
        )
        self.client.cookies["view_mode"] = "desktop"

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "delivery-map-shell")
        self.assertContains(response, "checkout-delivery-map.js")
        self.assertContains(response, "Start typing your address and choose the exact result")
        self.assertNotContains(response, "maps.googleapis.com/maps/api/js?key=")

    @override_settings(
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
    )
    def test_delivery_validation_accepts_inside_radius_and_rejects_outside(self):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        inside_details = {
            "line1": "12 Test Street",
            "line2": "",
            "city": "Leeds",
            "postcode": "LS1 1AA",
            "formatted_address": "12 Test Street, Leeds LS1 1AA, UK",
            "place_id": "inside-place",
            "latitude": Decimal("53.801000"),
            "longitude": Decimal("-1.548000"),
            "distance_miles": None,
        }
        validate_service_details(Order.ServiceType.DELIVERY, inside_details)
        self.assertIsNotNone(inside_details["distance_miles"])

        outside_details = {
            **inside_details,
            "latitude": Decimal("51.507400"),
            "longitude": Decimal("-0.127800"),
            "distance_miles": None,
        }
        with self.assertRaisesMessage(ValidationError, "outside our 3 mile delivery area"):
            validate_service_details(Order.ServiceType.DELIVERY, outside_details)

    @override_settings(
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        GOOGLE_MAPS_SERVER_API_KEY="test-server-key",
        GOOGLE_ADDRESS_VALIDATION_ENABLED=True,
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
    )
    @patch("apps.orders.services.requests.post")
    def test_google_address_validation_updates_delivery_address_metadata(self, mock_post):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": {
                "verdict": {"addressComplete": True},
                "address": {"formattedAddress": "12 Test Street, Leeds LS1 1AA, UK"},
                "geocode": {"location": {"latitude": 53.801, "longitude": -1.548}},
            }
        }
        mock_post.return_value = mock_response
        delivery_details = {
            "line1": "12 Test Street",
            "line2": "",
            "city": "Leeds",
            "postcode": "LS1 1AA",
            "formatted_address": "",
            "place_id": "inside-place",
            "latitude": Decimal("53.801000"),
            "longitude": Decimal("-1.548000"),
            "distance_miles": None,
        }

        validate_service_details(Order.ServiceType.DELIVERY, delivery_details)

        mock_post.assert_called_once()
        self.assertEqual(delivery_details["formatted_address"], "12 Test Street, Leeds LS1 1AA, UK")
        self.assertEqual(delivery_details["latitude"], Decimal("53.801"))
        self.assertEqual(delivery_details["longitude"], Decimal("-1.548"))
        self.assertIsNotNone(delivery_details["distance_miles"])

    @override_settings(
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        GOOGLE_MAPS_SERVER_API_KEY="test-server-key",
        GOOGLE_ADDRESS_VALIDATION_ENABLED=True,
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
    )
    @patch("apps.orders.services.requests.post")
    def test_google_address_validation_rejects_incomplete_addresses(self, mock_post):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        mock_response = Mock()
        mock_response.json.return_value = {"result": {"verdict": {"addressComplete": False}}}
        mock_post.return_value = mock_response
        delivery_details = {
            "line1": "12 Test Street",
            "line2": "",
            "city": "Leeds",
            "postcode": "LS1 1AA",
            "formatted_address": "",
            "place_id": "inside-place",
            "latitude": Decimal("53.801000"),
            "longitude": Decimal("-1.548000"),
            "distance_miles": None,
        }

        with self.assertRaisesMessage(ValidationError, "complete delivery address"):
            validate_service_details(Order.ServiceType.DELIVERY, delivery_details)

    @override_settings(
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        GOOGLE_MAPS_SERVER_API_KEY="test-server-key",
        GOOGLE_ADDRESS_VALIDATION_ENABLED=True,
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
    )
    @patch("apps.orders.services.requests.post")
    def test_google_address_validation_api_failure_falls_back_to_local_radius_check(self, mock_post):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        mock_post.side_effect = requests.RequestException("timeout")
        delivery_details = {
            "line1": "12 Test Street",
            "line2": "",
            "city": "Leeds",
            "postcode": "LS1 1AA",
            "formatted_address": "12 Test Street, Leeds LS1 1AA, UK",
            "place_id": "inside-place",
            "latitude": Decimal("53.801000"),
            "longitude": Decimal("-1.548000"),
            "distance_miles": None,
        }

        validate_service_details(Order.ServiceType.DELIVERY, delivery_details)

        self.assertIsNotNone(delivery_details["distance_miles"])

    @override_settings(
        DEBUG=True,
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_delivery_checkout_post_stores_map_metadata(self):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        self.client.post(
            reverse("orders:add_to_cart"),
            {
                "menu_item_id": self.menu_item.pk,
                "quantity": 1,
                "modifiers": "[]",
                "service_type": Order.ServiceType.DELIVERY,
            },
            HTTP_ACCEPT="application/json",
        )

        response = self.client.post(
            reverse("payments:create"),
            {
                "service_type": Order.ServiceType.DELIVERY,
                "customer_name": "Delivery Customer",
                "customer_phone": "07747055935",
                "customer_email": "delivery@example.com",
                "delivery_address_line1": "12 Test Street",
                "delivery_city": "Leeds",
                "delivery_postcode": "LS1 1AA",
                "delivery_formatted_address": "12 Test Street, Leeds LS1 1AA, UK",
                "delivery_place_id": "inside-place",
                "delivery_latitude": "53.801000",
                "delivery_longitude": "-1.548000",
                "pickup_time": "30",
                "payment_method": "online",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.service_type, Order.ServiceType.DELIVERY)
        self.assertEqual(order.delivery_formatted_address, "12 Test Street, Leeds LS1 1AA, UK")
        self.assertEqual(order.delivery_place_id, "inside-place")
        self.assertIsNotNone(order.delivery_distance_miles)

    @override_settings(
        DEBUG=True,
        DELIVERY_ENABLED=True,
        GOOGLE_MAPS_API_KEY="test-google-key",
        SHOP_LATITUDE="53.800755",
        SHOP_LONGITUDE="-1.549077",
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_delivery_checkout_outside_radius_does_not_create_order(self):
        ensure_site_settings(
            delivery_enabled=True,
            delivery_map_enabled=True,
            delivery_radius_miles=Decimal("3.00"),
        )
        self.client.post(
            reverse("orders:add_to_cart"),
            {
                "menu_item_id": self.menu_item.pk,
                "quantity": 1,
                "modifiers": "[]",
                "service_type": Order.ServiceType.DELIVERY,
            },
            HTTP_ACCEPT="application/json",
        )

        response = self.client.post(
            reverse("payments:create"),
            {
                "service_type": Order.ServiceType.DELIVERY,
                "customer_name": "Delivery Customer",
                "customer_phone": "07747055935",
                "delivery_address_line1": "12 Test Street",
                "delivery_city": "London",
                "delivery_postcode": "SW1A 1AA",
                "delivery_formatted_address": "London SW1A 1AA, UK",
                "delivery_place_id": "outside-place",
                "delivery_latitude": "51.507400",
                "delivery_longitude": "-0.127800",
                "pickup_time": "30",
                "payment_method": "online",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    def test_confirmed_order_eta_uses_slowest_item_prep_snapshot(self):
        short_item = create_menu_item(name="Quick Side", price=Decimal("2.50"), preparation_time=10)
        slow_item = create_menu_item(name="Slow Stew", price=Decimal("7.50"), preparation_time=25)
        medium_item = create_menu_item(name="Medium Main", price=Decimal("5.50"), preparation_time=15)
        order = Order.objects.create(
            customer_name="Prep Customer",
            customer_phone="07747055935",
            subtotal=Decimal("15.50"),
            total_amount=Decimal("15.50"),
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PAID,
            requested_pickup_time=timezone.now() + timezone.timedelta(minutes=15),
        )
        for item in (short_item, slow_item, medium_item):
            OrderItem.objects.create(
                order=order,
                menu_item=item,
                item_name=item.name,
                item_price=item.price,
                quantity=1,
                modifiers=[],
            )

        before = timezone.now()
        order.update_status(Order.OrderStatus.CONFIRMED)
        after = timezone.now()

        order.refresh_from_db()
        self.assertGreaterEqual(order.estimated_ready_time, before + timezone.timedelta(minutes=25))
        self.assertLessEqual(order.estimated_ready_time, after + timezone.timedelta(minutes=25, seconds=1))

    def test_order_eta_uses_snapshot_after_menu_prep_time_changes(self):
        item = create_menu_item(name="Stew", price=Decimal("7.50"), preparation_time=20)
        order = Order.objects.create(
            customer_name="Snapshot Customer",
            customer_phone="07747055935",
            subtotal=Decimal("7.50"),
            total_amount=Decimal("7.50"),
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PAID,
            requested_pickup_time=timezone.now() + timezone.timedelta(minutes=15),
        )
        OrderItem.objects.create(
            order=order,
            menu_item=item,
            item_name=item.name,
            item_price=item.price,
            quantity=1,
            modifiers=[],
        )
        item.preparation_time = 60
        item.save(update_fields=["preparation_time"])

        before = timezone.now()
        order.update_status(Order.OrderStatus.CONFIRMED)
        after = timezone.now()

        order.refresh_from_db()
        self.assertGreaterEqual(order.estimated_ready_time, before + timezone.timedelta(minutes=20))
        self.assertLessEqual(order.estimated_ready_time, after + timezone.timedelta(minutes=20, seconds=1))

    def test_order_eta_survives_deleted_menu_item_link(self):
        item = create_menu_item(name="Archived Item", price=Decimal("7.50"), preparation_time=30)
        order = Order.objects.create(
            customer_name="Deleted Link Customer",
            customer_phone="07747055935",
            subtotal=Decimal("7.50"),
            total_amount=Decimal("7.50"),
            status=Order.OrderStatus.PENDING,
            payment_status=Order.PaymentStatus.PAID,
            requested_pickup_time=timezone.now() + timezone.timedelta(minutes=15),
        )
        OrderItem.objects.create(
            order=order,
            menu_item=item,
            item_name=item.name,
            item_price=item.price,
            quantity=1,
            modifiers=[],
        )
        item.delete()

        before = timezone.now()
        order.update_status(Order.OrderStatus.CONFIRMED)
        after = timezone.now()

        order.refresh_from_db()
        self.assertGreaterEqual(order.estimated_ready_time, before + timezone.timedelta(minutes=30))
        self.assertLessEqual(order.estimated_ready_time, after + timezone.timedelta(minutes=30, seconds=1))

    def test_pay_instore_is_blocked_for_customer_checkout(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        response = self.client.post(
            reverse("orders:pay_instore"),
            {
                "customer_name": "Online Only",
                "customer_phone": "07747055935",
                "customer_email": "guest@example.com",
                "pickup_time": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:checkout"))
        self.assertEqual(Order.objects.count(), 0)
        self.assertNotEqual(self.client.session.get("cart"), {})

    def test_delivery_order_requires_online_payment_for_pay_instore(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("orders:add_to_cart"),
            {
                "menu_item_id": self.menu_item.pk,
                "quantity": 1,
                "modifiers": "[]",
                "service_type": Order.ServiceType.DELIVERY,
            },
            HTTP_ACCEPT="application/json",
        )
        response = self.client.post(
            reverse("orders:pay_instore"),
            {
                "service_type": Order.ServiceType.DELIVERY,
                "customer_name": "Delivery Customer",
                "customer_phone": "07747055935",
                "delivery_address_line1": "12 Test Street",
                "delivery_city": "Leeds",
                "delivery_postcode": "LS1 1AA",
                "pickup_time": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_is_online_payment_only_on_desktop_and_mobile(self):
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )

        desktop_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(desktop_response.status_code, 200)
        self.assertContains(desktop_response, "Pay Online")
        desktop_content = desktop_response.content.decode()
        self.assertTrue("Pay £" in desktop_content or "Place Order - Pay Shop" in desktop_content)
        self.assertNotContains(desktop_response, "Pay in Store")
        self.assertNotContains(desktop_response, "Pay when you collect")
        self.assertNotContains(desktop_response, 'orders:pay_instore')

        self.client.cookies["view_mode"] = "mobile"
        mobile_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(mobile_response.status_code, 200)
        self.assertContains(mobile_response, "Pay Online")
        mobile_content = mobile_response.content.decode()
        self.assertTrue("Pay £" in mobile_content or "Place Order - Pay Shop" in mobile_content)
        self.assertNotContains(mobile_response, "Pay in Store")
        self.assertNotContains(mobile_response, "Pay when you collect")

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        PAYMENT_FALLBACK_ENABLED=True,
        PAYMENT_FALLBACK_HOLD_MINUTES=15,
    )
    def test_mobile_checkout_keeps_fallback_acknowledgement_checkbox(self):
        ensure_site_settings(
            phone="+441131234567",
            address="45 High Street, Leeds LS1 1AA",
        )
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        self.client.cookies["view_mode"] = "mobile"

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="paymentAvailabilityMessage"')
        self.assertContains(response, 'name="payment_fallback_acknowledged"')
        self.assertContains(response, "I understand I must pay the shop within 15 minutes")
        self.assertContains(response, 'href="tel:+441131234567"')
        self.assertContains(response, "Call store")
        self.assertContains(response, "Get directions")
        self.assertContains(
            response,
            "https://www.google.com/maps/search/?api=1&query=45%20High%20Street%2C%20Leeds%20LS1%201AA",
        )
        self.assertNotContains(response, "paymentAlert.textContent")

        self.client.cookies["view_mode"] = "desktop"
        desktop_response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(desktop_response.status_code, 200)
        self.assertContains(desktop_response, 'href="tel:+441131234567"')
        self.assertContains(desktop_response, "Call store")
        self.assertContains(desktop_response, "Get directions")

    def test_staff_boards_and_tracking_render(self):
        order = create_order(
            user=self.user,
            status=Order.OrderStatus.PREPARING,
            payment_status=Order.PaymentStatus.PAID,
        )
        tracking_response = self.client.get(reverse("orders:tracking", args=[order.order_number]))
        self.assertEqual(tracking_response.status_code, 200)
        self.assertContains(tracking_response, "This page refreshes automatically")
        self.assertContains(tracking_response, order.items.first().item_name)

        manager_group, _ = Group.objects.get_or_create(name=OPERATIONS_MANAGER_GROUP)
        self.staff_user.groups.add(manager_group)
        self.client.force_login(self.staff_user)
        for url in [
            reverse("orders:order_board"),
            reverse("orders:order_list_fragment"),
            reverse("orders:kanban_board"),
            reverse("orders:kanban_column", args=["preparing"]),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

        update_response = self.client.post(
            reverse("orders:update_order_status", args=[order.id]),
            {"status": Order.OrderStatus.READY},
        )
        self.assertEqual(update_response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.READY)

    def test_confirmation_pages_link_to_tracking(self):
        order = create_order(user=self.user)
        tracking_url = reverse("orders:tracking", args=[order.order_number])

        for name in ["orders:confirmation", "orders:confirmation_instore"]:
            with self.subTest(template="desktop", route=name):
                response = self.client.get(reverse(name, args=[order.order_number]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, tracking_url)
                self.assertContains(response, "Track Order")

            with self.subTest(template="mobile", route=name):
                response = self.client.get(
                    reverse(name, args=[order.order_number]),
                    HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, tracking_url)
                self.assertContains(response, "Track Order")

    def test_delivery_tracking_renders_out_for_delivery_state(self):
        order = create_order(
            user=self.user,
            status=Order.OrderStatus.OUT_FOR_DELIVERY,
            service_type=Order.ServiceType.DELIVERY,
            delivery_address_line1="12 Test Street",
            delivery_city="Leeds",
            delivery_postcode="LS1 1AA",
        )
        response = self.client.get(reverse("orders:tracking", args=[order.order_number]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Out for Delivery")


class PaymentFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_site_settings()
        self.user = create_user()
        self.menu_item = create_menu_item()
        self.voucher = create_voucher()

    def _seed_cart(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        session = self.client.session
        session["voucher_code"] = self.voucher.code
        session.save()

    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_create_payment_redirects_to_demo_checkout_in_debug(self):
        self._seed_cart()
        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Debug User",
                "customer_phone": "07747055935",
                "customer_email": "debug@example.com",
                "pickup_time": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.latest("id")
        self.assertIn(reverse("payments:demo_checkout", args=[order.order_number]), response.url)
        self.assertTrue(Payment.objects.filter(order=order).exists())
        self.assertTrue(VoucherUsage.objects.filter(order=order).exists())

    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_create_payment_persists_delivery_details(self):
        self._seed_cart()
        session = self.client.session
        session["service_type"] = Order.ServiceType.DELIVERY
        session.save()

        response = self.client.post(
            reverse("payments:create"),
            {
                "service_type": Order.ServiceType.DELIVERY,
                "customer_name": "Delivery User",
                "customer_phone": "07747055935",
                "customer_email": "delivery@example.com",
                "delivery_address_line1": "12 Test Street",
                "delivery_city": "Leeds",
                "delivery_postcode": "LS1 1AA",
                "pickup_time": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.latest("id")
        self.assertEqual(order.service_type, Order.ServiceType.DELIVERY)
        self.assertEqual(order.delivery_address_line1, "12 Test Street")
        self.assertEqual(order.delivery_city, "Leeds")
        self.assertEqual(order.delivery_postcode, "LS1 1AA")

    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_guest_voucher_limit_blocks_payment_creation(self):
        limited_offer = create_offer(
            name="Guest Once Online",
            value=Decimal("2.00"),
            offer_type=Offer.OfferType.FIXED,
        )
        voucher = create_voucher(code="GUESTPAY", offer=limited_offer)
        voucher.max_uses_per_customer = 1
        voucher.save(update_fields=["max_uses_per_customer"])
        create_order(
            customer_phone="07747055935",
            voucher_code=voucher.code,
            applied_offer=limited_offer,
            discount_amount=Decimal("2.00"),
            total_amount=Decimal("10.50"),
        )

        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 1, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )
        session = self.client.session
        session["voucher_code"] = voucher.code
        session.save()

        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Guest Payer",
                "customer_phone": "07747 055935",
                "customer_email": "guest@example.com",
                "pickup_time": "15",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:checkout"))
        self.assertEqual(Order.objects.filter(voucher_code=voucher.code).count(), 1)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertNotIn("voucher_code", self.client.session)

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_online_payment_fails_closed_without_api_key_in_production_mode(self):
        self._seed_cart()
        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Prod User",
                "customer_phone": "07747055935",
                "customer_email": "prod@example.com",
                "pickup_time": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_live_key",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_online_payment_fails_closed_without_webhook_secret(self):
        self._seed_cart()
        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Prod User",
                "customer_phone": "07747055935",
                "customer_email": "prod@example.com",
                "pickup_time": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        PAYMENT_FALLBACK_ENABLED=True,
        PAYMENT_FALLBACK_HOLD_MINUTES=15,
    )
    def test_unavailable_online_payment_prompts_for_fallback_acknowledgement(self):
        self._seed_cart()
        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Fallback User",
                "customer_phone": "07747055935",
                "customer_email": "fallback@example.com",
                "pickup_time": "15",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn("payment_fallback_prompt", self.client.session)

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        PAYMENT_FALLBACK_ENABLED=True,
        PAYMENT_FALLBACK_HOLD_MINUTES=15,
    )
    def test_acknowledged_payment_fallback_creates_held_unpaid_order(self):
        self._seed_cart()
        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Fallback User",
                "customer_phone": "07747055935",
                "customer_email": "fallback@example.com",
                "pickup_time": "15",
                "payment_fallback_acknowledged": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.latest("id")
        payment = order.payment
        self.assertEqual(order.status, Order.OrderStatus.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(payment.provider, Payment.Provider.OFFLINE_PENDING)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNotNone(payment.expires_at)
        self.assertIn(reverse("payments:return", args=[order.order_number]), response.url)

    def test_offline_pending_payment_status_shows_call_and_directions_actions(self):
        ensure_site_settings(
            phone="+441131234567",
            address="45 High Street, Leeds LS1 1AA",
        )
        order = create_order(status=Order.OrderStatus.PENDING, payment_status=Order.PaymentStatus.PENDING)
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_pending_actions",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(minutes=15),
        )

        response = self.client.get(reverse("payments:return", args=[order.order_number]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your order is being held for payment.")
        self.assertContains(response, "Shop phone:")
        self.assertContains(response, "+441131234567")
        self.assertContains(response, 'href="tel:+441131234567"')
        self.assertContains(response, "Call store")
        self.assertContains(response, "Get directions")
        self.assertContains(
            response,
            "https://www.google.com/maps/search/?api=1&query=45%20High%20Street%2C%20Leeds%20LS1%201AA",
        )
        self.assertContains(response, "Track order")

        tracking_response = self.client.get(reverse("orders:tracking", args=[order.order_number]))
        self.assertEqual(tracking_response.status_code, 200)
        self.assertContains(tracking_response, 'href="tel:+441131234567"')
        self.assertContains(tracking_response, "Call store")
        self.assertContains(tracking_response, "Get directions")
        self.assertContains(
            tracking_response,
            "https://www.google.com/maps/search/?api=1&query=45%20High%20Street%2C%20Leeds%20LS1%201AA",
        )

        self.client.cookies["view_mode"] = "desktop"
        desktop_tracking_response = self.client.get(reverse("orders:tracking", args=[order.order_number]))
        self.assertEqual(desktop_tracking_response.status_code, 200)
        self.assertContains(desktop_tracking_response, 'href="tel:+441131234567"')
        self.assertContains(desktop_tracking_response, "Call store")
        self.assertContains(desktop_tracking_response, "Get directions")

    def test_offline_pending_payment_status_hides_missing_contact_actions(self):
        ensure_site_settings(phone="", address="")
        order = create_order(status=Order.OrderStatus.PENDING, payment_status=Order.PaymentStatus.PENDING)
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_pending_no_contact",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
            expires_at=timezone.now() + timezone.timedelta(minutes=15),
        )

        response = self.client.get(reverse("payments:return", args=[order.order_number]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your order is being held for payment.")
        self.assertNotContains(response, "Call store")
        self.assertNotContains(response, "Get directions")
        self.assertNotContains(response, "Shop phone:")
        self.assertContains(response, "Track order")

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_valid_123",
        STRIPE_WEBHOOK_SECRET="whsec_valid_123",
        PAYMENT_FALLBACK_ENABLED=True,
        PAYMENT_FALLBACK_HOLD_MINUTES=15,
    )
    @patch("apps.payments.views.payment_service_for_provider")
    def test_provider_failure_prompts_then_allows_fallback_order(self, mocked_provider_factory):
        self._seed_cart()
        service = Mock()
        service.create_payment.side_effect = RuntimeError("stripe down")
        mocked_provider_factory.return_value = service

        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Provider Error",
                "customer_phone": "07747055935",
                "customer_email": "provider@example.com",
                "pickup_time": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.session["payment_fallback_prompt"]["reason"], "provider_error")

        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Provider Error",
                "customer_phone": "07747055935",
                "customer_email": "provider@example.com",
                "pickup_time": "15",
                "payment_fallback_acknowledged": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.latest("id")
        self.assertEqual(order.payment.provider, Payment.Provider.OFFLINE_PENDING)

    def test_expire_unpaid_orders_cancels_expired_fallback_payment(self):
        order = create_order(status=Order.OrderStatus.PENDING, payment_status=Order.PaymentStatus.PENDING)
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.OFFLINE_PENDING,
            external_payment_id="offline_expired",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),
        )

        call_command("expire_unpaid_orders", verbosity=0)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.EXPIRED)
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)

    @override_settings(
        DEBUG=False,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_live_key",
        STRIPE_WEBHOOK_SECRET="whsec_test",
    )
    @patch("apps.payments.views.payment_service_for_provider")
    def test_create_payment_uses_stripe_provider_when_configured(self, mocked_provider_factory):
        self._seed_cart()
        service = Mock()

        def _create_payment(order, request):
            return Payment.objects.create(
                order=order,
                provider=Payment.Provider.STRIPE,
                external_payment_id="cs_test_123",
                amount=order.total_amount,
                currency="GBP",
                status=Payment.Status.PENDING,
                checkout_url="https://checkout.stripe.test/session",
            )

        service.create_payment.side_effect = _create_payment
        mocked_provider_factory.return_value = service

        response = self.client.post(
            reverse("payments:create"),
            {
                "customer_name": "Stripe User",
                "customer_phone": "07747055935",
                "customer_email": "stripe@example.com",
                "pickup_time": "15",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.stripe.test/session")
        payment = Payment.objects.latest("id")
        self.assertEqual(payment.provider, Payment.Provider.STRIPE)
        mocked_provider_factory.assert_called_once()

    @override_settings(
        DEBUG=True,
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_demo_checkout_marks_order_paid(self):
        order = create_order(user=self.user, status=Order.OrderStatus.PENDING)
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.DEMO,
            external_payment_id="demo_123",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )
        response = self.client.post(reverse("payments:demo_checkout", args=[order.order_number]), {"action": "pay"})
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    @patch("apps.payments.views.refresh_payment_status")
    def test_payment_status_api_returns_current_state(self, mocked_refresh):
        order = create_order(user=self.user, payment_status=Order.PaymentStatus.PAID)
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.DEMO,
            external_payment_id="demo_123",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PAID,
        )
        response = self.client.get(reverse("payments:status", args=[order.order_number]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["paid"])
        mocked_refresh.assert_not_called()

    @override_settings(
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_live_key",
        STRIPE_WEBHOOK_SECRET="whsec_test",
    )
    @patch("apps.payments.views.StripePaymentService.update_payment_status")
    @patch("apps.payments.views.stripe.Webhook.construct_event")
    def test_webhook_rejects_invalid_signature_and_accepts_valid_event(
        self,
        mocked_construct_event,
        mocked_update,
    ):
        order = create_order(user=self.user, status=Order.OrderStatus.PENDING)
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.STRIPE,
            external_payment_id="cs_test_123",
            amount=order.total_amount,
            currency="GBP",
            status=Payment.Status.PENDING,
        )

        from apps.payments.views import stripe_error

        mocked_construct_event.side_effect = stripe_error.SignatureVerificationError(
            message="Invalid signature",
            sig_header="bad",
        )
        rejected = self.client.post(
            reverse("payments:webhook"),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 403)
        mocked_update.assert_not_called()

        mocked_construct_event.side_effect = None
        mocked_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "status": "complete",
                    "payment_status": "paid",
                    "payment_method_types": ["card"],
                }
            },
        }
        mocked_update.return_value = payment
        accepted = self.client.post(
            reverse("payments:webhook"),
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(accepted.status_code, 200)
        mocked_update.assert_called_once_with(
            "cs_test_123",
            payload={
                "id": "cs_test_123",
                "status": "complete",
                "payment_status": "paid",
                "payment_method_types": ["card"],
            },
            event_type="checkout.session.completed",
        )
