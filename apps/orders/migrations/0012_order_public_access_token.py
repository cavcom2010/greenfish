from django.db import migrations, models

from apps.orders.models import generate_public_access_token


def backfill_public_access_tokens(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.filter(public_access_token="").only("id", "public_access_token"):
        token = generate_public_access_token()
        while Order.objects.filter(public_access_token=token).exists():
            token = generate_public_access_token()
        order.public_access_token = token
        order.save(update_fields=["public_access_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0011_orderissue"),
    ]

    operations = [
            migrations.AddField(
                model_name="order",
                name="public_access_token",
                field=models.CharField(blank=True, editable=False, max_length=64),
            ),
            migrations.RunPython(backfill_public_access_tokens, migrations.RunPython.noop),
            migrations.AlterField(
                model_name="order",
                name="public_access_token",
                field=models.CharField(
                    default=generate_public_access_token,
                    editable=False,
                    max_length=64,
                unique=True,
            ),
        ),
    ]
