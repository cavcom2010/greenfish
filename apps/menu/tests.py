from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.test_support import create_menu_item


class MenuItemPrepTimeTests(TestCase):
    def test_menu_item_preparation_time_must_be_at_least_one_minute(self):
        item = create_menu_item(price=Decimal("6.50"), preparation_time=0)

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_menu_item_preparation_time_accepts_owner_configured_minutes(self):
        item = create_menu_item(price=Decimal("6.50"), preparation_time=25)

        item.full_clean()
        self.assertEqual(item.preparation_time, 25)
