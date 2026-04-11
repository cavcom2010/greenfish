from django.db import migrations


def backfill_order_operations(apps, schema_editor):
    Order = apps.get_model("orders", "Order")

    for order in Order.objects.all().iterator():
        dirty_fields = []
        accepted_at = order.accepted_at
        completed_at = order.completed_at
        ready_at = order.ready_at

        if order.status in {"confirmed", "preparing", "ready", "completed"} and not order.accepted_at:
            accepted_at = order.paid_at or order.created_at
            order.accepted_at = accepted_at
            dirty_fields.append("accepted_at")

        if order.status in {"preparing", "ready", "completed"} and not order.preparing_started_at:
            order.preparing_started_at = accepted_at or order.created_at
            dirty_fields.append("preparing_started_at")

        if order.actual_ready_time and not order.ready_at:
            ready_at = order.actual_ready_time
            order.ready_at = ready_at
            dirty_fields.append("ready_at")

        if order.status in {"ready", "completed"} and not order.ready_at:
            ready_at = order.actual_ready_time or order.updated_at
            order.ready_at = ready_at
            dirty_fields.append("ready_at")

        if order.status == "completed" and not order.completed_at:
            completed_at = order.updated_at
            order.completed_at = completed_at
            dirty_fields.append("completed_at")

        if order.status == "cancelled" and not order.cancelled_at:
            order.cancelled_at = order.updated_at
            dirty_fields.append("cancelled_at")

        if order.service_type == "delivery" and order.status in {"ready", "completed"} and not order.dispatched_at:
            order.dispatched_at = ready_at or order.updated_at
            dirty_fields.append("dispatched_at")

        if order.service_type == "delivery" and order.status == "completed" and not order.delivered_at:
            order.delivered_at = completed_at or order.updated_at
            dirty_fields.append("delivered_at")

        if order.service_type == "pickup" and order.status == "completed" and not order.collected_at:
            order.collected_at = completed_at or order.updated_at
            dirty_fields.append("collected_at")

        if dirty_fields:
            order.save(update_fields=dirty_fields)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_order_accepted_at_order_accepted_by_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_order_operations, noop_reverse),
    ]
