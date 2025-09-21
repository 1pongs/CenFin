from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        (
            "liabilities",
            "0008_rename_current_balance_creditcard_available_credit_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="loan",
            name="interest_paid",
            field=models.DecimalField(
                default=Decimal("0"), max_digits=12, decimal_places=2
            ),
        ),
    ]
