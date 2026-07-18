import os
import subprocess
import sys
import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.core.media import build_variant_name, get_image_variant_url
from apps.core.models import LargeOrderRequest, NotificationEvent
from apps.core.test_support import create_meal_deal, create_menu_item, create_offer, create_order, create_user, ensure_site_settings
from apps.menu.models import MenuCategory, MenuItem
from apps.orders.models import Order


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
            reverse("core:large_orders"),
            reverse("menu:menu"),
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

    def test_contact_page_has_call_and_directions_actions(self):
        ensure_site_settings(
            phone="+441131234567",
            address="45 High Street, Leeds LS1 1AA",
        )

        response = self.client.get(reverse("core:contact"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="tel:+441131234567"')
        self.assertContains(response, "Get directions")
        self.assertContains(
            response,
            "https://www.google.com/maps/search/?api=1&query=45%20High%20Street%2C%20Leeds%20LS1%201AA",
        )

        self.client.cookies["view_mode"] = "desktop"
        desktop_response = self.client.get(reverse("core:contact"))
        self.assertEqual(desktop_response.status_code, 200)
        self.assertContains(desktop_response, 'href="tel:+441131234567"')
        self.assertContains(desktop_response, "Get directions")

    def test_favicon_ico_redirects_to_app_icon(self):
        response = self.client.get("/favicon.ico")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/static/icons/icon-192.png")

    def test_large_order_request_captures_customer_and_basket_snapshot(self):
        self.client.post(
            reverse("orders:add_to_cart"),
            {"menu_item_id": self.menu_item.pk, "quantity": 3, "modifiers": "[]"},
            HTTP_ACCEPT="application/json",
        )

        response = self.client.post(
            reverse("core:large_orders"),
            {
                "name": "Office Manager",
                "company_name": "Acme Ltd",
                "phone": "07747055935",
                "email": "office@example.com",
                "event_datetime": "2026-12-24T12:30",
                "service_type": "pickup",
                "delivery_address": "",
                "postcode": "",
                "guest_count": "30",
                "requested_items": "Lunch for the team",
            },
        )

        self.assertRedirects(response, reverse("core:large_orders"))
        large_order = LargeOrderRequest.objects.get()
        self.assertEqual(large_order.company_name, "Acme Ltd")
        self.assertEqual(large_order.status, LargeOrderRequest.Status.NEW)
        self.assertEqual(large_order.basket_snapshot["items"][0]["quantity"], 3)
        self.assertEqual(large_order.estimated_total, self.menu_item.price * 3)
        self.assertTrue(
            NotificationEvent.objects.filter(
                channel=NotificationEvent.Channel.EMAIL,
                event_type="large_order_request_received",
                recipient="office@example.com",
            ).exists()
        )

    def test_large_order_delivery_requires_address_or_postcode(self):
        response = self.client.post(
            reverse("core:large_orders"),
            {
                "name": "Office Manager",
                "company_name": "Acme Ltd",
                "phone": "07747055935",
                "email": "office@example.com",
                "event_datetime": "2026-12-24T12:30",
                "service_type": "delivery",
                "delivery_address": "",
                "postcode": "",
                "guest_count": "30",
                "requested_items": "Lunch for the team",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LargeOrderRequest.objects.count(), 0)
        self.assertContains(response, "Please add a delivery address or postcode")

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
        self.assertContains(html_response, "Request a large order")

        # Phones get the same unified partial (rendered as a bottom sheet).
        mobile_html_response = self.client.get(
            reverse("menu:item_detail", args=[self.menu_item.pk]),
            HTTP_HX_REQUEST="true",
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        )
        self.assertEqual(mobile_html_response.status_code, 200)
        self.assertContains(mobile_html_response, 'id="modalAddBtn"')
        self.assertContains(mobile_html_response, "Request a large order")

        json_response = self.client.get(
            reverse("menu:item_detail", args=[self.menu_item.pk]),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["name"], self.menu_item.name)

    def test_menu_page_carries_filter_contract_and_home_is_shop_window(self):
        category = MenuCategory.objects.create(name="Sides", sort_order=2, is_active=True, icon="🍟")
        side_item = create_menu_item(
            name="Spicy Chips",
            category=category,
            dietary_tags=["vegetarian"],
            is_popular=False,
        )

        # Menu page renders every item with the client-side filter contract:
        # category/dietary pills, search, and data attributes on each card.
        # ?category= only seeds the initial pill state.
        response = self.client.get(
            reverse("menu:menu"),
            {"category": category.id},
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="menuGrid"')
        self.assertContains(response, side_item.name)
        self.assertContains(response, self.menu_item.name)
        self.assertContains(response, 'data-menu-category=""')
        self.assertContains(response, "data-menu-dietary")
        self.assertContains(response, f'data-category-id="{self.menu_item.category_id}"')
        self.assertContains(response, f'data-category-id="{side_item.category_id}"')
        self.assertContains(response, "openItemModal")
        self.assertContains(response, "quickAddToCart")
        self.assertEqual(response.context["active_category"], category)

        # Home is the shop window: no embedded full-menu grid, category
        # chips link into the menu page instead.
        home_response = self.client.get(
            reverse("core:home"),
            HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        )
        self.assertEqual(home_response.status_code, 200)
        self.assertNotContains(home_response, 'id="menuGrid"')
        self.assertNotContains(home_response, "data-menu-category")
        self.assertContains(home_response, 'class="category-chip"')
        self.assertContains(home_response, f'{reverse("menu:menu")}?category={category.id}')

    def test_category_fragment_renders(self):
        response = self.client.get(
            reverse("menu:category_items", args=[self.menu_item.category_id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.menu_item.name)

    def test_menu_cards_expose_dietary_tags_for_client_side_filtering(self):
        category = self.menu_item.category
        create_menu_item(
            name="Veg Sadza",
            category=category,
            dietary_tags=["vegetarian", "vegan"],
            is_popular=False,
        )

        response = self.client.get(reverse("menu:menu"), {"dietary": "vegetarian"})

        self.assertEqual(response.status_code, 200)
        # Dietary filtering happens client-side against these attributes;
        # the query param just marks the pill active on load.
        self.assertContains(response, 'data-dietary-tags="vegetarian,vegan"')
        self.assertEqual(response.context["dietary_filter"], "vegetarian")

    def test_home_order_again_only_includes_reorderable_orders(self):
        user = create_user(email="home-repeat@example.com")
        eligible = create_order(
            user=user,
            status=Order.OrderStatus.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
            collected_at=timezone.now(),
            customer_email="eligible-home@example.com",
        )
        ineligible = create_order(
            user=user,
            status=Order.OrderStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.PAID,
            customer_email="blocked-home@example.com",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(eligible, response.context["recent_orders"])
        self.assertNotIn(ineligible, response.context["recent_orders"])

    def test_account_pages_require_login_and_auth_pages_render(self):
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)
        self.assertEqual(self.client.get(reverse("accounts:order_history")).status_code, 302)
        self.assertEqual(self.client.get(reverse("account_login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_signup")).status_code, 200)

        user = create_user(email="account@example.com")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:order_history")).status_code, 200)

    def test_unified_shell_renders_for_every_device_class(self):
        """One responsive template tree serves phones, tablets, and desktop."""
        home_url = reverse("core:home")
        offline_url = reverse("pwa:offline")
        user_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 14; SM-X200) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
            "Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36",
        ]

        for ua in user_agents:
            with self.subTest(ua=ua):
                response = self.client.get(home_url, HTTP_USER_AGENT=ua)
                self.assertContains(response, 'class="site-header"')
                self.assertContains(response, 'class="bottom-nav"')
                self.assertContains(response, 'id="mobileMenuOverlay"')
                self.assertNotContains(response, 'class="mobile-container"')
                offline_response = self.client.get(offline_url, HTTP_USER_AGENT=ua)
                self.assertContains(offline_response, 'class="site-header"')
                self.assertNotContains(offline_response, 'class="mobile-container"')


class ProductionSettingsEmailTests(TestCase):
    def _run_production_settings_probe(self, env_lines):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("\n".join(env_lines))
            env_file.write("\n")
            env_path = env_file.name

        probe_env = os.environ.copy()
        probe_env["ENV_FILE"] = env_path
        probe_env["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
        probe_env.pop("EMAIL_BACKEND", None)
        probe_env.pop("EMAIL_HOST", None)
        probe_env.pop("EMAIL_HOST_USER", None)
        probe_env.pop("EMAIL_HOST_PASSWORD", None)
        probe_env.pop("RESEND_API_KEY", None)
        probe_env.pop("SENDGRID_API_KEY", None)

        try:
            return subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import importlib; "
                        "settings = importlib.import_module('config.settings.production'); "
                        "print(settings.EMAIL_BACKEND)"
                    ),
                ],
                cwd=Path(__file__).resolve().parents[2],
                env=probe_env,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            Path(env_path).unlink(missing_ok=True)

    def _required_production_env(self):
        return [
            "DJANGO_SECRET_KEY=prod-secret-abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "DJANGO_ALLOWED_HOSTS=example.com,www.example.com",
            "DATABASE_URL=postgres://user:pass@localhost:5432/greenfish",
            "PAYMENT_PROVIDER=stripe",
            "STRIPE_SECRET_KEY=sk_live_example",
            "STRIPE_WEBHOOK_SECRET=whsec_example",
            "EMAIL_HOST=smtp.gmail.com",
            "EMAIL_HOST_USER=orders@example.com",
            "EMAIL_HOST_PASSWORD=app-password",
        ]

    def test_production_uses_smtp_with_google_workspace_defaults(self):
        result = self._run_production_settings_probe(self._required_production_env())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("django.core.mail.backends.smtp.EmailBackend", result.stdout)

    def test_production_uses_smtp_when_smtp_credentials_are_present(self):
        env_lines = self._required_production_env() + [
            "EMAIL_HOST=smtp.example.com",
            "EMAIL_HOST_USER=orders@example.com",
            "EMAIL_HOST_PASSWORD=app-password",
        ]
        result = self._run_production_settings_probe(env_lines)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("django.core.mail.backends.smtp.EmailBackend", result.stdout)

    def test_production_uses_explicit_email_backend_when_set(self):
        env_lines = self._required_production_env() + [
            "EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend",
            "EMAIL_HOST=smtp.example.com",
        ]
        result = self._run_production_settings_probe(env_lines)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("django.core.mail.backends.smtp.EmailBackend", result.stdout)

    def test_local_settings_can_use_mailpit_smtp_from_env(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("\n".join([
                "EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend",
                "EMAIL_HOST=127.0.0.1",
                "EMAIL_PORT=1025",
                "EMAIL_USE_TLS=False",
            ]))
            env_file.write("\n")
            env_path = env_file.name

        probe_env = os.environ.copy()
        probe_env["ENV_FILE"] = env_path
        probe_env["DJANGO_SETTINGS_MODULE"] = "config.settings.local"

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import importlib; "
                        "settings = importlib.import_module('config.settings.local'); "
                        "print(settings.EMAIL_BACKEND); "
                        "print(settings.EMAIL_HOST); "
                        "print(settings.EMAIL_PORT); "
                        "print(settings.EMAIL_USE_TLS)"
                    ),
                ],
                cwd=Path(__file__).resolve().parents[2],
                env=probe_env,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("django.core.mail.backends.smtp.EmailBackend", result.stdout)
        self.assertIn("127.0.0.1", result.stdout)
        self.assertIn("1025", result.stdout)
        self.assertIn("False", result.stdout)

    def test_local_settings_blank_email_backend_uses_console(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("EMAIL_BACKEND=\n")
            env_path = env_file.name

        probe_env = os.environ.copy()
        probe_env["ENV_FILE"] = env_path
        probe_env["DJANGO_SETTINGS_MODULE"] = "config.settings.local"

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import importlib; "
                        "settings = importlib.import_module('config.settings.local'); "
                        "print(settings.EMAIL_BACKEND)"
                    ),
                ],
                cwd=Path(__file__).resolve().parents[2],
                env=probe_env,
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("django.core.mail.backends.console.EmailBackend", result.stdout)

    def test_production_still_requires_payment_credentials(self):
        env_lines = [
            line for line in self._required_production_env()
            if not line.startswith("STRIPE_WEBHOOK_SECRET=")
        ] + ["PAYMENT_FALLBACK_ENABLED=False"]
        result = self._run_production_settings_probe(env_lines)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Valid Stripe credentials are required", result.stderr)

    def test_runtime_entrypoints_default_to_production_settings(self):
        for module_name in ["config.wsgi", "config.asgi", "config.celery"]:
            with self.subTest(module=module_name):
                with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
                    env_file.write("\n".join(self._required_production_env()))
                    env_file.write("\n")
                    env_path = env_file.name

                probe_env = os.environ.copy()
                probe_env["ENV_FILE"] = env_path
                probe_env.pop("DJANGO_SETTINGS_MODULE", None)

                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            (
                                "import os, importlib; "
                                f"importlib.import_module('{module_name}'); "
                                "print(os.environ.get('DJANGO_SETTINGS_MODULE'))"
                            ),
                        ],
                        cwd=Path(__file__).resolve().parents[2],
                        env=probe_env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                finally:
                    Path(env_path).unlink(missing_ok=True)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("config.settings.production", result.stdout)


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


class OpeningHoursServiceTests(TestCase):
    HOURS = {"0": {"open": "11:00", "close": "22:00"}}

    def _at(self, weekday, hour, minute=0):
        # 2026-07-13 is a Monday (weekday 0)
        from datetime import datetime, timedelta

        from django.utils import timezone as tz

        base = datetime(2026, 7, 13, hour, minute)
        return tz.make_aware(base + timedelta(days=weekday))

    def test_rows_normalise_structured_hours(self):
        from apps.core.services.opening_hours import opening_hours_rows

        rows, text = opening_hours_rows(self.HOURS)
        self.assertEqual(text, "")
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0], {"day": "Monday", "open": "11:00", "close": "22:00"})
        self.assertEqual(rows[1]["open"], "")

    def test_rows_pass_through_free_text(self):
        from apps.core.services.opening_hours import opening_hours_rows

        rows, text = opening_hours_rows("Ring us for opening times")
        self.assertEqual(rows, [])
        self.assertEqual(text, "Ring us for opening times")

    def test_status_open_and_closed_transitions(self):
        from apps.core.services.opening_hours import opening_status

        open_now = opening_status(self.HOURS, now=self._at(0, 12))
        self.assertTrue(open_now["is_open"])
        self.assertIn("22:00", open_now["label"])

        before_open = opening_status(self.HOURS, now=self._at(0, 9))
        self.assertFalse(before_open["is_open"])
        self.assertIn("11:00", before_open["label"])

        after_close = opening_status(self.HOURS, now=self._at(0, 23))
        self.assertFalse(after_close["is_open"])

        closed_day = opening_status(self.HOURS, now=self._at(1, 12))
        self.assertFalse(closed_day["is_open"])
        self.assertEqual(closed_day["label"], "Closed today")

    def test_status_handles_overnight_closing(self):
        from apps.core.services.opening_hours import opening_status

        hours = {"0": {"open": "17:00", "close": "01:00"}}
        self.assertTrue(opening_status(hours, now=self._at(0, 23))["is_open"])
        self.assertFalse(opening_status(hours, now=self._at(0, 12))["is_open"])

    def test_status_none_for_unstructured_hours(self):
        from apps.core.services.opening_hours import opening_status

        self.assertIsNone(opening_status("Ring us"))
        self.assertIsNone(opening_status({}))
