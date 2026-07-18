from django.core.files.storage import default_storage
from django.db import migrations

# Photos of the headline dish in each seed deal; the files (and their
# __card/__thumb variants) are the tracked menu-item photos, so no new
# media is needed. Deals with an admin-uploaded image are left alone,
# and unknown deployments (different deal names, missing media) no-op.
DEAL_IMAGES = {
    "Kids Box": "menu/items/chicken-nugget-pixabay-246180.jpg",
    "Chinese Box A": "menu/items/spare-ribs-in-salt-pepper-pixabay-4369041.jpg",
}


def assign_images(apps, schema_editor):
    MealDeal = apps.get_model("mealdeals", "MealDeal")
    for name, path in DEAL_IMAGES.items():
        if default_storage.exists(path):
            MealDeal.objects.filter(name=name, image="").update(image=path)


def clear_images(apps, schema_editor):
    MealDeal = apps.get_model("mealdeals", "MealDeal")
    for name, path in DEAL_IMAGES.items():
        MealDeal.objects.filter(name=name, image=path).update(image="")


class Migration(migrations.Migration):

    dependencies = [
        ("mealdeals", "0002_alter_mealdeal_image"),
    ]

    operations = [
        migrations.RunPython(assign_images, clear_images),
    ]
