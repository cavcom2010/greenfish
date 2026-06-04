from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0012_order_public_access_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="personal_data_anonymised_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
