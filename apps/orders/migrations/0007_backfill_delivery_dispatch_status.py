from django.db import migrations


def move_legacy_delivery_ready_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(
        service_type="delivery",
        status="ready",
    ).update(status="out_for_delivery")


def reverse_legacy_delivery_ready_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(
        service_type="delivery",
        status="out_for_delivery",
    ).update(status="ready")


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0006_alter_order_status"),
    ]

    operations = [
        migrations.RunPython(
            move_legacy_delivery_ready_orders,
            reverse_legacy_delivery_ready_orders,
        ),
    ]
