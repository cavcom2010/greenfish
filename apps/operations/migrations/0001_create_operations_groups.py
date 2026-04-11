from django.db import migrations


GROUP_NAMES = [
    "Operations Manager",
    "Operations Kitchen",
    "Operations Cashier",
]


def create_operations_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def delete_operations_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_operations_groups, delete_operations_groups),
    ]
