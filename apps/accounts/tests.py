from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomerProfile, SavedMeal
from apps.core.test_support import create_menu_item, create_order, create_user, ensure_site_settings


class RepeatOrderExperienceTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.user = create_user(email="repeat@example.com")
        self.client.force_login(self.user)
        self.item = create_menu_item(name="Saved Sadza", price=Decimal("6.50"))
        self.profile, _ = CustomerProfile.objects.get_or_create(user=self.user)

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
        order = create_order(user=self.user)
        order_item = order.items.first()
        order_item.menu_item = self.item
        order_item.item_name = self.item.name
        order_item.item_price = self.item.price
        order_item.quantity = 2
        order_item.modifiers = [{"id": 1, "name": "Extra Gravy", "price": "0.50"}]
        order_item.save()

        response = self.client.post(reverse("accounts:reorder", args=[order.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("orders:cart"))
        cart = self.client.session["cart"]
        stored_item = next(iter(cart.values()))
        self.assertEqual(stored_item["menu_item_id"], self.item.pk)
        self.assertEqual(stored_item["quantity"], 2)
        self.assertEqual(stored_item["modifiers"][0]["name"], "Extra Gravy")

    def test_order_history_links_to_order_tracking(self):
        order = create_order(user=self.user)
        response = self.client.get(reverse("accounts:order_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("orders:tracking", args=[order.order_number]))
        self.assertContains(response, "Track")

    def test_customer_cannot_reorder_someone_elses_order(self):
        other_user = create_user(email="other@example.com")
        order = create_order(user=other_user)

        response = self.client.post(reverse("accounts:reorder", args=[order.pk]))

        self.assertEqual(response.status_code, 404)

    def test_customer_can_save_past_order_item_as_meal_and_add_it_again(self):
        order = create_order(user=self.user)
        order_item = order.items.first()
        order_item.menu_item = self.item
        order_item.item_name = self.item.name
        order_item.item_price = self.item.price
        order_item.quantity = 2
        order_item.modifiers = [{"id": 1, "name": "Extra Gravy", "price": "0.50"}]
        order_item.save()

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

    def test_save_meal_next_redirect_rejects_external_urls(self):
        order = create_order(user=self.user)
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
