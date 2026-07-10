from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.test_support import create_meal_deal, create_menu_item
from apps.mealdeals.models import MealDeal


class MealDealPricingTests(TestCase):
    def test_savings_and_savings_percent_properties(self):
        deal = MealDeal.objects.create(
            name="Combo",
            original_price=Decimal("10.00"),
            deal_price=Decimal("8.00"),
        )

        self.assertEqual(deal.savings, Decimal("2.00"))
        self.assertEqual(deal.savings_percent, 20)

    def test_savings_percent_is_zero_when_original_price_is_zero(self):
        deal = MealDeal.objects.create(
            name="Free Add-on",
            original_price=Decimal("0.00"),
            deal_price=Decimal("0.00"),
        )

        self.assertEqual(deal.savings_percent, 0)


class MealDealListViewTests(TestCase):
    def test_deal_list_only_shows_active_deals(self):
        active_deal = create_meal_deal(create_menu_item(name="Active Main"))
        inactive_deal = create_meal_deal(create_menu_item(name="Inactive Main"))
        inactive_deal.is_active = False
        inactive_deal.save(update_fields=["is_active"])

        response = self.client.get(reverse("mealdeals:list"))

        self.assertEqual(response.status_code, 200)
        deals = list(response.context["deals"])
        self.assertIn(active_deal, deals)
        self.assertNotIn(inactive_deal, deals)


class MealDealDetailViewTests(TestCase):
    def test_detail_404_for_inactive_deal(self):
        deal = create_meal_deal(create_menu_item())
        deal.is_active = False
        deal.save(update_fields=["is_active"])

        response = self.client.get(reverse("mealdeals:detail", args=[deal.id]))

        self.assertEqual(response.status_code, 404)

    def test_detail_404_for_missing_deal(self):
        response = self.client.get(reverse("mealdeals:detail", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def test_detail_includes_items_and_options(self):
        menu_item = create_menu_item(name="Deal Main")
        deal = create_meal_deal(menu_item)

        response = self.client.get(reverse("mealdeals:detail", args=[deal.id]))

        self.assertEqual(response.status_code, 200)
        context_deal = response.context["deal"]
        items = list(context_deal.items.all())
        self.assertEqual(len(items), 1)
        options = list(items[0].options.all())
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].menu_item, menu_item)
