from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomerProfile
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
