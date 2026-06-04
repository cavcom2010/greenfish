import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_notificationevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="order_personal_data_retention_years",
            field=models.PositiveSmallIntegerField(
                default=6,
                help_text="Years to keep customer-identifying order details before anonymisation. Business totals and item records are retained.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(20),
                ],
            ),
        ),
    ]
