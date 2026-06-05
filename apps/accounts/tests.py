from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from apps.accounts.models import CustomerProfile, SavedMeal
from apps.core.test_support import create_menu_item, create_order, create_user, ensure_site_settings
from apps.orders.models import Order


class AuthProxyIPTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        cache.clear()

    def test_mobile_login_accepts_forwarded_client_ip(self):
        user = create_user(email="mobile-login@example.com", password="password123")

        response = self.client.post(
            reverse("account_login"),
            {"login": user.email, "password": "password123"},
            HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 10; Mobile)",
            HTTP_X_FORWARDED_FOR="198.51.100.44",
            REMOTE_ADDR="",
        )

        self.assertNotEqual(response.status_code, 403)
        self.assertEqual(response.status_code, 302)


class RepeatOrderExperienceTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="repeat@example.com")
        self.client.force_login(self.user)
        self.item = create_menu_item(name="Saved Sadza", price=Decimal("6.50"))
        self.profile, _ = CustomerProfile.objects.get_or_create(user=self.user)

    def _reorderable_pickup_order(self, **overrides):
        defaults = {
            "user": self.user,
            "status": Order.OrderStatus.COMPLETED,
            "payment_status": Order.PaymentStatus.PAID,
            "service_type": Order.ServiceType.PICKUP,
            "collected_at": timezone.now(),
        }
        defaults.update(overrides)
        return create_order(**defaults)

    def _point_order_at_item(self, order, quantity=2):
        order_item = order.items.first()
        order_item.menu_item = self.item
        order_item.item_name = self.item.name
        order_item.item_price = self.item.price
        order_item.quantity = quantity
        order_item.modifiers = [{"id": 1, "name": "Extra Gravy", "price": "0.50"}]
        order_item.save()
        return order_item

    def test_customer_can_save_and_remove_favorite_item(self):
        response = self.client.post(reverse("accounts:toggle_favorite", args=[self.item.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.profile.favorite_items.filter(pk=self.item.pk).exists())

        response = self.client.post(
            reverse("accounts:toggle_favorite", args=[self.item.pk]),
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_favorite"])
        self.assertFalse(self.profile.favorite_items.filter(pk=self.item.pk).exists())

    def test_favorite_next_redirect_rejects_external_urls(self):
        response = self.client.post(
            reverse("accounts:toggle_favorite", args=[self.item.pk]),
            {"next": "https://evil.example/phish"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    def test_favorite_next_redirect_allows_local_urls(self):
        response = self.client.post(
            reverse("accounts:toggle_favorite", args=[self.item.pk]),
            {"next": reverse("accounts:app_home")},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:app_home"))

    def test_customer_can_add_saved_favorite_to_cart(self):
        self.profile.favorite_items.add(self.item)

        response = self.client.post(reverse("accounts:add_favorite_to_cart", args=[self.item.pk]))

        self.assertEqual(response.status_code, 302)
        cart = self.client.session["cart"]
        self.assertEqual(len(cart), 1)
        stored_item = next(iter(cart.values()))
        self.assertEqual(stored_item["name"], self.item.name)
        self.assertEqual(stored_item["quantity"], 1)

    def test_customer_can_reorder_available_items_from_previous_order(self):
        order = self._reorderable_pickup_order()
        self._point_order_at_item(order)

        response = self.client.post(reverse("accounts:reorder", args=[order.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:cart"))
        cart = self.client.session["cart"]
        stored_item = next(iter(cart.values()))
        self.assertEqual(stored_item["menu_item_id"], self.item.pk)
        self.assertEqual(stored_item["quantity"], 2)
        self.assertEqual(stored_item["modifiers"][0]["name"], "Extra Gravy")

    def test_customer_can_reorder_completed_paid_delivery_order(self):
        order = create_order(
            user=self.user,
            status=Order.OrderStatus.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
            service_type=Order.ServiceType.DELIVERY,
            delivered_at=timezone.now(),
        )
        self._point_order_at_item(order, quantity=1)

        response = self.client.post(reverse("accounts:reorder", args=[order.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:cart"))
        stored_item = next(iter(self.client.session["cart"].values()))
        self.assertEqual(stored_item["menu_item_id"], self.item.pk)

    def test_customer_cannot_reorder_orders_without_successful_handover(self):
        cases = [
            {
                "label": "pending unpaid",
                "status": Order.OrderStatus.PENDING,
                "payment_status": Order.PaymentStatus.PENDING,
            },
            {
                "label": "confirmed paid",
                "status": Order.OrderStatus.CONFIRMED,
                "payment_status": Order.PaymentStatus.PAID,
            },
            {
                "label": "cancelled paid",
                "status": Order.OrderStatus.CANCELLED,
                "payment_status": Order.PaymentStatus.PAID,
                "collected_at": timezone.now(),
            },
            {
                "label": "completed unpaid",
                "status": Order.OrderStatus.COMPLETED,
                "payment_status": Order.PaymentStatus.PENDING,
                "collected_at": timezone.now(),
            },
            {
                "label": "completed refunded",
                "status": Order.OrderStatus.COMPLETED,
                "payment_status": Order.PaymentStatus.REFUNDED,
                "collected_at": timezone.now(),
            },
            {
                "label": "completed paid without collection",
                "status": Order.OrderStatus.COMPLETED,
                "payment_status": Order.PaymentStatus.PAID,
            },
            {
                "label": "completed paid delivery without delivery",
                "status": Order.OrderStatus.COMPLETED,
                "payment_status": Order.PaymentStatus.PAID,
                "service_type": Order.ServiceType.DELIVERY,
            },
        ]

        for index, case in enumerate(cases):
            with self.subTest(case=case["label"]):
                order = create_order(user=self.user, customer_email=f"blocked-{index}@example.com", **{
                    key: value for key, value in case.items() if key != "label"
                })

                response = self.client.post(reverse("accounts:reorder", args=[order.pk]))

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("accounts:order_history"))
                self.assertEqual(self.client.session.get("cart", {}), {})

    def test_order_history_links_to_order_tracking(self):
        order = create_order(user=self.user)
        response = self.client.get(reverse("accounts:order_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("orders:tracking", args=[order.order_number]))
        self.assertContains(response, "Track")

    def test_order_history_is_paginated(self):
        for index in range(12):
            create_order(user=self.user, customer_email=f"page-{index}@example.com")

        response = self.client.get(reverse("accounts:order_history"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["orders"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_order_history_filters_by_status_and_service(self):
        delivery_order = create_order(
            user=self.user,
            status=Order.OrderStatus.COMPLETED,
            service_type=Order.ServiceType.DELIVERY,
            customer_email="delivery-history@example.com",
        )
        create_order(
            user=self.user,
            status=Order.OrderStatus.CANCELLED,
            service_type=Order.ServiceType.PICKUP,
            customer_email="pickup-history@example.com",
        )

        response = self.client.get(
            reverse("accounts:order_history"),
            {"status": Order.OrderStatus.COMPLETED, "service": Order.ServiceType.DELIVERY},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["orders"]), [delivery_order])

    def test_order_history_filters_by_date_window(self):
        recent_order = create_order(user=self.user, customer_email="recent-history@example.com")
        old_order = create_order(user=self.user, customer_email="old-history@example.com")
        Order.objects.filter(pk=old_order.pk).update(created_at=timezone.now() - timezone.timedelta(days=90))

        response = self.client.get(reverse("accounts:order_history"), {"date": "30d"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(recent_order, response.context["orders"])
        self.assertNotIn(old_order, response.context["orders"])

    def test_customer_can_claim_matching_guest_order_with_token(self):
        order = create_order(user=None, customer_email=self.user.email)
        claim_url = f"{reverse('accounts:claim_guest_order', args=[order.order_number])}?t={order.public_access_token}"

        response = self.client.post(claim_url)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.user, self.user)

    def test_customer_cannot_claim_guest_order_with_wrong_email(self):
        order = create_order(user=None, customer_email="someone-else@example.com")
        claim_url = f"{reverse('accounts:claim_guest_order', args=[order.order_number])}?t={order.public_access_token}"

        response = self.client.post(claim_url)

        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertIsNone(order.user)

    def test_customer_cannot_claim_guest_order_without_token(self):
        order = create_order(user=None, customer_email=self.user.email)

        response = self.client.post(reverse("accounts:claim_guest_order", args=[order.order_number]))

        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertIsNone(order.user)

    def test_customer_cannot_reorder_someone_elses_order(self):
        other_user = create_user(email="other@example.com")
        order = create_order(user=other_user)

        response = self.client.post(reverse("accounts:reorder", args=[order.pk]))

        self.assertEqual(response.status_code, 404)

    def test_customer_can_save_past_order_item_as_meal_and_add_it_again(self):
        order = self._reorderable_pickup_order()
        order_item = self._point_order_at_item(order)

        response = self.client.post(reverse("accounts:save_order_item_meal", args=[order_item.pk]))

        self.assertEqual(response.status_code, 302)
        saved_meal = SavedMeal.objects.get(user=self.user, menu_item=self.item)
        self.assertEqual(saved_meal.quantity, 2)
        self.assertEqual(saved_meal.modifiers[0]["name"], "Extra Gravy")

        response = self.client.post(reverse("accounts:add_saved_meal_to_cart", args=[saved_meal.pk]))

        self.assertEqual(response.status_code, 302)
        stored_item = next(iter(self.client.session["cart"].values()))
        self.assertEqual(stored_item["quantity"], 2)
        self.assertEqual(stored_item["modifiers"][0]["name"], "Extra Gravy")

    def test_customer_cannot_save_meal_from_unfinished_order(self):
        order = create_order(user=self.user, status=Order.OrderStatus.CONFIRMED, payment_status=Order.PaymentStatus.PAID)
        order_item = self._point_order_at_item(order)

        response = self.client.post(reverse("accounts:save_order_item_meal", args=[order_item.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:order_history"))
        self.assertFalse(SavedMeal.objects.filter(user=self.user, menu_item=self.item).exists())

    def test_save_meal_next_redirect_rejects_external_urls(self):
        order = self._reorderable_pickup_order()
        order_item = order.items.first()
        order_item.menu_item = self.item
        order_item.save()

        response = self.client.post(
            reverse("accounts:save_order_item_meal", args=[order_item.pk]),
            {"next": "https://evil.example/phish"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:app_home"))

    def test_logout_requires_post_to_end_session(self):
        response = self.client.get(reverse("account_logout"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("_auth_user_id", self.client.session)

        response = self.client.post(reverse("account_logout"))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_desktop_login_posts_credentials(self):
        self.client.logout()

        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": "password123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_app_home_renders_rewards_and_saved_meals(self):
        SavedMeal.objects.create(
            user=self.user,
            menu_item=self.item,
            name="Lunch favourite",
            item_name=self.item.name,
            item_price=self.item.price,
            quantity=1,
            modifiers=[],
        )

        response = self.client.get(reverse("accounts:app_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rewards Hub")
        self.assertContains(response, "Lunch favourite")

    def test_app_home_recent_orders_only_include_reorderable_orders(self):
        eligible = self._reorderable_pickup_order(customer_email="eligible-app-home@example.com")
        ineligible = create_order(
            user=self.user,
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.PAID,
            customer_email="blocked-app-home@example.com",
        )

        response = self.client.get(reverse("accounts:app_home"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(eligible, response.context["recent_orders"])
        self.assertNotIn(ineligible, response.context["recent_orders"])

    def test_order_history_hides_reorder_actions_for_ineligible_orders(self):
        eligible = self._reorderable_pickup_order(customer_email="eligible-history@example.com")
        ineligible = create_order(
            user=self.user,
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.PAID,
            customer_email="blocked-history@example.com",
        )

        response = self.client.get(reverse("accounts:order_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("orders:tracking", args=[eligible.order_number]))
        self.assertContains(response, reverse("orders:tracking", args=[ineligible.order_number]))
        self.assertContains(response, reverse("accounts:reorder", args=[eligible.pk]), count=1)
        self.assertNotContains(response, reverse("accounts:reorder", args=[ineligible.pk]))
