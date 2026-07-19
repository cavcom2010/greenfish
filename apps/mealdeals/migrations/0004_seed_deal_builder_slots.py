from decimal import Decimal

from django.db import migrations

# Builder slots for the two seed deals, matching their descriptions and
# mapped to existing menu items by exact name. Same-price alternatives are
# offered as free swaps; the one priced upgrade mirrors the menu price gap
# (Chips £2.30 → Salt & Pepper Chips £3.80) and can be adjusted in admin.
# Deals that already have slots, unknown deal names, and missing menu items
# all no-op, so other client deployments are unaffected.
DEAL_SLOTS = {
    "Kids Box": [
        ("Choose your main", [
            ("Chicken Nugget (8 pcs)", Decimal("0.00")),
            ("Sausages", Decimal("0.00")),
            ("Battered Sausages", Decimal("0.00")),
        ]),
        ("Choose your side", [
            ("Chips", Decimal("0.00")),
            ("Salt & Pepper Chips", Decimal("1.50")),
        ]),
        ("Your drink", [
            ("Can of Drinks", Decimal("0.00")),
        ]),
    ],
    "Chinese Box A": [
        ("Ribs (4 pcs)", [
            ("Spare Ribs in Salt & Pepper", Decimal("0.00")),
            ("Spare Ribs in BBQ Sauce", Decimal("0.00")),
        ]),
        ("Chips", [
            ("Salt & Pepper Chips", Decimal("0.00")),
            ("Chips", Decimal("0.00")),
        ]),
        ("Chicken", [
            ("Salt & Pepper Chicken Wings", Decimal("0.00")),
        ]),
        ("Spring rolls", [
            ("Vegetable Spring Rolls (8 pcs)", Decimal("0.00")),
        ]),
        ("Samosa", [
            ("Curry Samosa (12 pcs)", Decimal("0.00")),
        ]),
        ("Sweet & sour", [
            ("Sweet & Sour Chicken", Decimal("0.00")),
        ]),
        ("Noodles", [
            ("Plain Noodle", Decimal("0.00")),
        ]),
        ("Rice", [
            ("Egg Fried Rice", Decimal("0.00")),
        ]),
        ("Sauce", [
            ("Curry Sauce", Decimal("0.00")),
            ("Sweet & Sour Sauce", Decimal("0.00")),
        ]),
    ],
}


def seed_slots(apps, schema_editor):
    MealDeal = apps.get_model("mealdeals", "MealDeal")
    MealDealItem = apps.get_model("mealdeals", "MealDealItem")
    MealDealOption = apps.get_model("mealdeals", "MealDealOption")
    MenuItem = apps.get_model("menu", "MenuItem")

    for deal_name, slots in DEAL_SLOTS.items():
        deal = MealDeal.objects.filter(name=deal_name).first()
        if deal is None or deal.items.exists():
            continue
        for sort_order, (slot_name, options) in enumerate(slots):
            menu_items = [
                (MenuItem.objects.filter(name=item_name, is_available=True).first(), upgrade)
                for item_name, upgrade in options
            ]
            menu_items = [(mi, upgrade) for mi, upgrade in menu_items if mi is not None]
            if not menu_items:
                continue
            slot = MealDealItem.objects.create(
                deal=deal,
                name=slot_name,
                min_quantity=1,
                max_quantity=1,
                sort_order=sort_order,
            )
            for menu_item, upgrade in menu_items:
                MealDealOption.objects.create(
                    deal_item=slot,
                    menu_item=menu_item,
                    upgrade_price=upgrade,
                    is_available=True,
                )


def clear_slots(apps, schema_editor):
    MealDealItem = apps.get_model("mealdeals", "MealDealItem")
    MealDealItem.objects.filter(deal__name__in=DEAL_SLOTS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mealdeals", "0003_seed_deal_images"),
        ("menu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_slots, clear_slots),
    ]
