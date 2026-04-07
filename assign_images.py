#!/usr/bin/env python3
"""Assign downloaded images to menu items."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from apps.menu.models import MenuItem

# Map image filenames to menu item names
IMAGE_MAPPING = {
    "sadza.jpg": ["Sadza (Isitshwala)", "Sadza ReMasau"],
    "beef_stew.jpg": ["Beef Stew (Nyama Yehombe)", "Braised Beef (Braised)"],
    "chicken_stew.jpg": ["Chicken Stew (Huku)"],
    "muriwo.jpg": ["Muriwo (Green Vegetables)", "Pumpkin Leaves (Muboora)", "Cabbage"],
    "tbone.jpg": ["Grilled T-Bone"],
    "goat_meat.jpg": ["Goat Meat (Mbudzi)", "Mazondo (Beef Trotters)", "Maguru (Tripe)"],
    "dovi_chicken.jpg": ["Dovi Chicken"],
    "mageu.jpg": ["Mageu", "Maheu"],
    "meal_combo.jpg": ["Kapenta"],
    "rice_beans.jpg": ["Rice & Beans"],
}

MEDIA_PATH = "menu/items/"

assigned = 0
not_found = []

for filename, item_names in IMAGE_MAPPING.items():
    full_path = f"{MEDIA_PATH}{filename}"
    
    for item_name in item_names:
        try:
            item = MenuItem.objects.get(name=item_name)
            item.image = full_path
            item.save()
            print(f"✓ Assigned {filename} to '{item_name}'")
            assigned += 1
        except MenuItem.DoesNotExist:
            print(f"✗ Menu item not found: '{item_name}'")
            not_found.append(item_name)

print(f"\n{'='*50}")
print(f"Assigned images to {assigned} menu items")

if not_found:
    print(f"\nNot found: {not_found}")

# List items without images
print("\nItems still without images:")
for item in MenuItem.objects.filter(image=""):
    print(f"  - {item.name}")
