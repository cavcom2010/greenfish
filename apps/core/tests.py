import os
import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.core.media import build_variant_name, get_image_variant_url
from apps.core.test_support import create_meal_deal, create_menu_item, create_offer, create_user, ensure_site_settings
from apps.menu.models import MenuCategory, MenuItem


class PublicRouteTests(TestCase):
    def setUp(self):
        ensure_site_settings()
        self.menu_item = create_menu_item()
        self.offer = create_offer()
        self.deal = create_meal_deal(self.menu_item)

    def test_public_pages_render(self):
        urls = [
            reverse("core:health"),
            reverse("core:home"),
            reverse("core:about"),
            reverse("core:contact"),
            reverse("menu:menu"),
            reverse("offers:list"),
            reverse("offers:detail", args=[self.offer.pk]),
            reverse("mealdeals:list"),
            reverse("mealdeals:detail", args=[self.deal.pk]),
            reverse("pwa:offline"),
            reverse("pwa:service_worker"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_health_endpoint_reports_database_state(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")

        with patch("apps.core.views.connection.cursor", side_effect=RuntimeError("db unavailable")):
            degraded = self.client.get(reverse("core:health"))
        self.assertEqual(degraded.status_code, 503)
        self.assertEqual(degraded.json()["status"], "degraded")
        self.assertEqual(degraded.json()["database"], "error")

    def test_menu_item_detail_supports_html_and_json(self):
        html_response = self.client.get(
            reverse("menu:item_detail", args=[self.menu_item.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, self.menu_item.name)
        self.assertContains(html_response, 'class="desktop-item-detail"')

        mobile_html_response = self.client.get(
            reverse("menu:item_detail", args=[self.menu_item.pk]),
            HTTP_HX_REQUEST="true",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        )
        self.assertEqual(mobile_html_response.status_code, 200)
        self.assertContains(mobile_html_response, 'id="modal-add-btn"')

        json_response = self.client.get(
            reverse("menu:item_detail", args=[self.menu_item.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["name"], self.menu_item.name)

    def test_category_fragment_renders(self):
        response = self.client.get(
            reverse("menu:category_items", args=[self.menu_item.category_id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.menu_item.name)

    def test_home_dietary_filter_works_on_sqlite(self):
        category = self.menu_item.category
        vegetarian_item = create_menu_item(
            name="Veg Sadza",
            category=category,
            dietary_tags=["vegetarian", "vegan"],
            is_popular=False,
        )
        non_matching_item = create_menu_item(
            name="Beef Sadza",
            category=category,
            dietary_tags=["halal"],
            is_popular=False,
        )

        response = self.client.get(
            reverse("core:home"),
            {"dietary": "vegetarian", "category": category.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["items"]), [vegetarian_item])
        self.assertNotIn(non_matching_item, response.context["items"])

    def test_account_pages_require_login_and_auth_pages_render(self):
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)
        self.assertEqual(self.client.get(reverse("accounts:order_history")).status_code, 302)
        self.assertEqual(self.client.get(reverse("account_login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_signup")).status_code, 200)

        user = create_user(email="account@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:order_history")).status_code, 200)

    def test_phone_tablet_and_cookie_layout_detection(self):
        home_url = reverse("core:home")
        offline_url = reverse("pwa:offline")
        phone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
        android_phone_ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36"
        android_tablet_ua = "Mozilla/5.0 (Linux; Android 14; SM-X200) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        ipad_ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"

        for ua in [phone_ua, android_phone_ua]:
            with self.subTest(device="phone", ua=ua):
                response = self.client.get(home_url, HTTP_USER_AGENT=ua)
                self.assertFalse(response.wsgi_request.is_desktop)
                self.assertContains(response, 'class="mobile-container"')
                self.assertNotContains(response, 'class="site-header"')
                offline_response = self.client.get(offline_url, HTTP_USER_AGENT=ua)
                self.assertContains(offline_response, 'class="mobile-container"')

        for ua in [android_tablet_ua, ipad_ua]:
            with self.subTest(device="tablet", ua=ua):
                response = self.client.get(home_url, HTTP_USER_AGENT=ua)
                self.assertTrue(response.wsgi_request.is_desktop)
                self.assertContains(response, 'class="site-header"')
                self.assertNotContains(response, 'class="mobile-container"')
                offline_response = self.client.get(offline_url, HTTP_USER_AGENT=ua)
                self.assertContains(offline_response, 'class="site-header"')
                self.assertNotContains(offline_response, 'class="mobile-container"')

        response = self.client.get(home_url, HTTP_USER_AGENT=phone_ua, HTTP_SEC_CH_UA_MOBILE="?0")
        self.assertFalse(response.wsgi_request.is_desktop)

        response = self.client.get(home_url, HTTP_USER_AGENT=android_tablet_ua, HTTP_SEC_CH_UA_MOBILE="?1")
        self.assertFalse(response.wsgi_request.is_desktop)

        self.client.cookies["view_mode"] = "desktop"
        response = self.client.get(home_url, HTTP_USER_AGENT=phone_ua)
        self.assertTrue(response.wsgi_request.is_desktop)

        self.client.cookies["view_mode"] = "mobile"
        response = self.client.get(home_url, HTTP_USER_AGENT=android_tablet_ua)
        self.assertFalse(response.wsgi_request.is_desktop)


class MediaHardeningTests(TestCase):
    def setUp(self):
        ensure_site_settings()

    def _image_upload(self, *, name="menu-item.png", size=(1200, 1200), fmt="PNG", noisy=False):
        if noisy:
            image = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
        else:
            image = Image.new("RGB", size, color=(255, 107, 53))

        buffer = BytesIO()
        image.save(buffer, format=fmt)
        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type=f"image/{fmt.lower()}",
        )

    def test_menu_item_upload_generates_optimized_variants(self):
        with tempfile.TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                item = create_menu_item(
                    name="Variant Sadza",
                    image=self._image_upload(),
                )

                card_variant = build_variant_name(item.image.name, "card")
                detail_variant = build_variant_name(item.image.name, "detail")

                self.assertTrue(Path(media_root, card_variant).exists())
                self.assertTrue(Path(media_root, detail_variant).exists())
                self.assertEqual(
                    get_image_variant_url(item.image, "card"),
                    item.image.storage.url(card_variant),
                )

    def test_menu_item_rejects_oversized_uploads(self):
        category = MenuCategory.objects.create(name="Large Uploads", is_active=True)
        item = MenuItem(
            category=category,
            name="Huge Sadza",
            price=Decimal("12.50"),
            image=self._image_upload(name="huge.png", size=(2100, 2100), noisy=True),
        )

        with self.assertRaises(ValidationError):
            item.save()
