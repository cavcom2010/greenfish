from django.db import migrations


OPERATIONS_GROUP_NAMES = [
    "Operations Manager",
    "Operations Kitchen",
    "Operations Cashier",
]


def backfill_staff_operations_manager(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")

    manager_group, _ = Group.objects.get_or_create(name="Operations Manager")
    operations_group_ids = list(
        Group.objects.filter(name__in=OPERATIONS_GROUP_NAMES).values_list("id", flat=True)
    )
    staff_without_ops_role = (
        User.objects.filter(is_staff=True)
        .exclude(groups__id__in=operations_group_ids)
        .distinct()
    )
    manager_group.user_set.add(*staff_without_ops_role)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_user_email"),
        ("operations", "0001_create_operations_groups"),
    ]

    operations = [
        migrations.RunPython(backfill_staff_operations_manager, noop_reverse),
    ]
