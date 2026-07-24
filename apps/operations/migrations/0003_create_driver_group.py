from django.db import migrations


GROUP_NAME = "Operations Driver"


def create_driver_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GROUP_NAME)


def delete_driver_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0002_backfill_staff_operations_manager"),
    ]

    operations = [
        migrations.RunPython(create_driver_group, delete_driver_group),
    ]
