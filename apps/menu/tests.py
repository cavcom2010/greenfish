from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test import override_settings
from PIL import Image

from django.core.cache import cache

from apps.core.test_support import create_menu_item, create_order
from apps.menu.models import MenuItem
from apps.menu.services import get_popular_menu_items
from apps.orders.models import Order, OrderItem


class PopularMenuItemsTests(TestCase):
    def setUp(self):
        cache.clear()
        # The seed migration ships flagged items; hide them so each test
        # controls exactly which items can rank.
        MenuItem.objects.update(is_available=False)

    def _paid_order_with(self, item, quantity, **order_overrides):
        order_overrides.setdefault("payment_status", Order.PaymentStatus.PAID)
        order = create_order(**order_overrides)
        # create_order seeds its own line; replace it with a controlled one
        order.items.all().delete()
        OrderItem.objects.create(
            order=order,
            menu_item=item,
            item_name=item.name,
            item_price=item.price,
            quantity=quantity,
            modifiers=[],
        )
        return order

    def test_ranks_by_distinct_orders_and_tops_up_with_flag(self):
        best_seller = create_menu_item(name="Best Seller", is_popular=False)
        catering_dish = create_menu_item(name="Catering Dish", is_popular=False)
        chefs_pick = create_menu_item(name="Chefs Pick", is_popular=True)

        # Two separate customers ordering one portion each outranks a
        # single 50-portion catering order.
        self._paid_order_with(best_seller, quantity=1)
        self._paid_order_with(best_seller, quantity=1)
        self._paid_order_with(catering_dish, quantity=50)

        items = get_popular_menu_items(limit=3)

        self.assertEqual(
            [item.name for item in items[:2]], ["Best Seller", "Catering Dish"]
        )
        # Not enough sales history for 3 slots: flag-popular item fills in.
        self.assertIn(chefs_pick, items)

    def test_meal_deal_components_count_toward_popularity(self):
        component = create_menu_item(name="Deal Component", is_popular=False)
        direct_seller = create_menu_item(name="Direct Seller", is_popular=False)

        # Deal purchases are stored with menu_item NULL and the chosen
        # component menu-item ids inside modifiers.
        for _ in range(2):
            order = create_order(payment_status=Order.PaymentStatus.PAID)
            order.items.all().delete()
            OrderItem.objects.create(
                order=order,
                menu_item=None,
                item_name="Family Feast Deal",
                item_price=component.price,
                quantity=1,
                modifiers=[
                    {"id": component.id, "name": f"Main: {component.name}", "price": "0.00"},
                    {"id": "not-a-number", "name": "Broken entry", "price": "0.00"},
                ],
            )
        self._paid_order_with(direct_seller, quantity=1)

        items = get_popular_menu_items(limit=2)

        self.assertEqual(
            [item.name for item in items], ["Deal Component", "Direct Seller"]
        )

    def test_ignores_unpaid_and_cancelled_orders(self):
        noise = create_menu_item(name="Noise Item", is_popular=False)
        seller = create_menu_item(name="Actual Seller", is_popular=False)

        self._paid_order_with(noise, quantity=50, payment_status=Order.PaymentStatus.PENDING)
        self._paid_order_with(noise, quantity=50, status=Order.OrderStatus.CANCELLED)
        self._paid_order_with(seller, quantity=1)

        items = get_popular_menu_items(limit=1)

        self.assertEqual([item.name for item in items], ["Actual Seller"])

    def test_unavailable_items_drop_out_even_when_ranking_is_cached(self):
        seller = create_menu_item(name="Sold Out Star", is_popular=False)
        backup = create_menu_item(name="Backup Flagged", is_popular=True)
        self._paid_order_with(seller, quantity=4)

        first = get_popular_menu_items(limit=1)
        self.assertEqual([item.name for item in first], ["Sold Out Star"])

        seller.is_available = False
        seller.save(update_fields=["is_available"])

        # Ranking ids are cached, but availability is re-checked per call.
        second = get_popular_menu_items(limit=1)
        self.assertEqual([item.name for item in second], ["Backup Flagged"])

    def test_survives_cache_backend_outage(self):
        seller = create_menu_item(name="Cacheless Seller", is_popular=False)
        self._paid_order_with(seller, quantity=3)

        # Production uses Redis; if it's down the homepage must still work.
        with patch("apps.menu.services.cache.get", side_effect=ConnectionError("redis down")), \
             patch("apps.menu.services.cache.set", side_effect=ConnectionError("redis down")):
            items = get_popular_menu_items(limit=1)

        self.assertEqual([item.name for item in items], ["Cacheless Seller"])

    def test_falls_back_to_flagged_items_without_order_history(self):
        create_menu_item(name="Unflagged", is_popular=False)
        flagged = create_menu_item(name="Flagged", is_popular=True)

        items = get_popular_menu_items(limit=6)

        self.assertEqual([item.id for item in items], [flagged.id])


class MenuItemPrepTimeTests(TestCase):
    def test_menu_item_preparation_time_must_be_at_least_one_minute(self):
        item = create_menu_item(price=Decimal("6.50"), preparation_time=0)

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_menu_item_preparation_time_accepts_owner_configured_minutes(self):
        item = create_menu_item(price=Decimal("6.50"), preparation_time=25)

        item.full_clean()
        self.assertEqual(item.preparation_time, 25)


class PixabayImageImportCommandTests(TestCase):
    def _image_bytes(self, color=(20, 90, 140)):
        buffer = BytesIO()
        Image.new("RGB", (900, 600), color=color).save(buffer, format="JPEG")
        return buffer.getvalue()

    def _response(self, *, json_data=None, content=b""):
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value=json_data or {})
        response.content = content
        return response

    @override_settings(PIXABAY_API_KEY="test-key")
    @patch("apps.menu.management.commands.fetch_menu_images.requests.get")
    def test_dry_run_writes_review_csv_without_saving_image(self, mock_get):
        item = create_menu_item(name="Chicken Stew")
        mock_get.return_value = self._response(
            json_data={
                "hits": [
                    {
                        "id": 123,
                        "pageURL": "https://pixabay.com/photos/chicken-stew-123/",
                        "user": "FoodPhotographer",
                        "previewURL": "https://cdn.example/preview.jpg",
                        "largeImageURL": "https://cdn.example/large.jpg",
                        "tags": "chicken, stew, food",
                    }
                ]
            }
        )

        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "candidates.csv"
            call_command("fetch_menu_images", "--dry-run", "--output", str(output))
            content = output.read_text(encoding="utf-8")

        item.refresh_from_db()
        self.assertFalse(item.image)
        self.assertIn("Chicken Stew", content)
        self.assertIn("https://cdn.example/large.jpg", content)
        self.assertIn("approved,item_id,item_name", content)

    @override_settings(PIXABAY_API_KEY="test-key")
    @patch("apps.menu.management.commands.fetch_menu_images.requests.get")
    def test_apply_approved_downloads_image_and_stores_source_metadata(self, mock_get):
        item = create_menu_item(name="Beef Stew")
        mock_get.return_value = self._response(content=self._image_bytes())

        with TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir) / "media"
            csv_path = Path(tmpdir) / "approved.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "approved,item_id,item_name,category,query,pixabay_id,page_url,contributor,preview_url,image_url,tags",
                        f"yes,{item.pk},Beef Stew,Mains,beef stew plate,456,https://pixabay.com/photos/beef-456/,ChefCam,,https://cdn.example/beef.jpg,\"beef, stew\"",
                    ]
                ),
                encoding="utf-8",
            )
            with override_settings(MEDIA_ROOT=media_root):
                call_command("fetch_menu_images", "--apply-approved", str(csv_path))

                item.refresh_from_db()
                self.assertTrue(item.image)
                self.assertTrue(item.image.storage.exists(item.image.name))
                self.assertEqual(item.image_source_metadata["provider"], "pixabay")
                self.assertEqual(item.image_source_metadata["pixabay_id"], "456")
                self.assertEqual(item.image_source_metadata["query"], "beef stew plate")
