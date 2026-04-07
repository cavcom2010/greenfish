"""
Add Zimbabwean menu categories and sample items.
"""
from decimal import Decimal

from django.db import migrations


def create_zimbabwean_menu(apps, schema_editor):
    """Create Zimbabwean menu categories and items."""
    MenuCategory = apps.get_model("menu", "MenuCategory")
    MenuItem = apps.get_model("menu", "MenuItem")
    MenuModifier = apps.get_model("menu", "MenuModifier")
    
    # Create categories
    categories = [
        {"name": "Sadza & Staples", "description": "Traditional Zimbabwean staple foods", "icon": "🌽", "sort_order": 1},
        {"name": "Nyama (Meat)", "description": "Beef, chicken, goat and traditional meats", "icon": "🍖", "sort_order": 2},
        {"name": "Muriwo (Vegetables)", "description": "Fresh vegetable sides and relishes", "icon": "🥬", "sort_order": 3},
        {"name": "Traditional Stews", "description": "Slow-cooked Zimbabwean stews", "icon": "🍲", "sort_order": 4},
        {"name": "Specialties", "description": "Zimbabwean delicacies and specialties", "icon": "⭐", "sort_order": 5},
        {"name": "Drinks", "description": "Traditional and modern beverages", "icon": "🥤", "sort_order": 6},
    ]
    
    created_categories = {}
    for cat_data in categories:
        cat, _ = MenuCategory.objects.get_or_create(
            name=cat_data["name"],
            defaults={
                "description": cat_data["description"],
                "icon": cat_data["icon"],
                "sort_order": cat_data["sort_order"],
            }
        )
        created_categories[cat_data["name"]] = cat
    
    # Create modifiers
    modifiers = [
        {"name": "Extra Sadza", "price_adjustment": Decimal("1.50")},
        {"name": "Extra Muriwo", "price_adjustment": Decimal("1.00")},
        {"name": "Extra Gravy", "price_adjustment": Decimal("0.50")},
        {"name": "Chilli Sauce", "price_adjustment": Decimal("0.00")},
    ]
    
    created_modifiers = {}
    for mod_data in modifiers:
        mod, _ = MenuModifier.objects.get_or_create(
            name=mod_data["name"],
            defaults={"price_adjustment": mod_data["price_adjustment"]}
        )
        created_modifiers[mod_data["name"]] = mod
    
    # Create menu items
    items = [
        # Sadza & Staples
        {
            "name": "Sadza (Isitshwala)",
            "description": "Traditional maize meal staple, smooth and filling",
            "price": Decimal("2.50"),
            "category": "Sadza & Staples",
            "is_popular": True,
        },
        {
            "name": "Sadza ReMasau",
            "description": "Sadza served with wild fruit relish",
            "price": Decimal("4.50"),
            "category": "Sadza & Staples",
        },
        {
            "name": "Rice & Beans",
            "description": "Steamed rice with sugar beans",
            "price": Decimal("3.50"),
            "category": "Sadza & Staples",
        },
        # Nyama
        {
            "name": "Beef Stew (Nyama Yehombe)",
            "description": "Slow-cooked beef in rich tomato and onion gravy",
            "price": Decimal("6.50"),
            "category": "Nyama (Meat)",
            "is_popular": True,
        },
        {
            "name": "Chicken Stew (Huku)",
            "description": "Tender chicken stewed with traditional spices",
            "price": Decimal("5.50"),
            "category": "Nyama (Meat)",
            "is_popular": True,
        },
        {
            "name": "Grilled T-Bone",
            "description": "Flame-grilled T-bone steak with Zimbabwean spices",
            "price": Decimal("8.50"),
            "category": "Nyama (Meat)",
        },
        {
            "name": "Goat Meat (Mbudzi)",
            "description": "Traditional goat meat stew",
            "price": Decimal("7.00"),
            "category": "Nyama (Meat)",
        },
        # Muriwo
        {
            "name": "Muriwo (Green Vegetables)",
            "description": "Fresh collard greens with onion and tomato",
            "price": Decimal("2.00"),
            "category": "Muriwo (Vegetables)",
            "is_popular": True,
        },
        {
            "name": "Pumpkin Leaves (Muboora)",
            "description": "Tender pumpkin leaves in peanut butter",
            "price": Decimal("2.50"),
            "category": "Muriwo (Vegetables)",
        },
        {
            "name": "Cabbage",
            "description": "Sautéed cabbage with tomatoes",
            "price": Decimal("1.50"),
            "category": "Muriwo (Vegetables)",
        },
        # Traditional Stews
        {
            "name": "Dovi Chicken",
            "description": "Chicken in creamy peanut butter sauce",
            "price": Decimal("6.00"),
            "category": "Traditional Stews",
            "is_popular": True,
        },
        {
            "name": "Braised Beef (Braised)",
            "description": "Beef slow-cooked with tomatoes and onions",
            "price": Decimal("6.50"),
            "category": "Traditional Stews",
        },
        # Specialties
        {
            "name": "Mazondo (Beef Trotters)",
            "description": "Traditional beef trotters, slow-cooked until tender",
            "price": Decimal("5.00"),
            "category": "Specialties",
        },
        {
            "name": "Maguru (Tripe)",
            "description": "Traditional tripe stew with onions",
            "price": Decimal("4.50"),
            "category": "Specialties",
        },
        {
            "name": "Kapenta",
            "description": "Dried silverfish, lightly fried with tomatoes",
            "price": Decimal("4.00"),
            "category": "Specialties",
        },
        # Drinks
        {
            "name": "Mageu",
            "description": "Traditional fermented maize drink",
            "price": Decimal("1.50"),
            "category": "Drinks",
        },
        {
            "name": "Maheu",
            "description": "Sweet fermented maize beverage",
            "price": Decimal("1.50"),
            "category": "Drinks",
        },
        {
            "name": "Zimbabwean Tea",
            "description": "Hot tea with milk",
            "price": Decimal("1.00"),
            "category": "Drinks",
        },
        {
            "name": "Soft Drink",
            "description": "Choice of Coca-Cola, Fanta, Sprite",
            "price": Decimal("1.50"),
            "category": "Drinks",
        },
    ]
    
    for item_data in items:
        category = created_categories.get(item_data["category"])
        if category:
            item, created = MenuItem.objects.get_or_create(
                name=item_data["name"],
                defaults={
                    "description": item_data["description"],
                    "price": item_data["price"],
                    "category": category,
                    "is_popular": item_data.get("is_popular", False),
                    "is_available": True,
                }
            )
            # Add modifiers to items
            if created:
                for mod_name, mod in created_modifiers.items():
                    item.modifiers.add(mod)


def reverse_migration(apps, schema_editor):
    """Reverse the migration."""
    MenuCategory = apps.get_model("menu", "MenuCategory")
    MenuCategory.objects.filter(
        name__in=[
            "Sadza & Staples",
            "Nyama (Meat)",
            "Muriwo (Vegetables)",
            "Traditional Stews",
            "Specialties",
            "Drinks",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_zimbabwean_menu, reverse_migration),
    ]
