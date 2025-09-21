from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("liabilities", "0009_loan_interest_paid"),
    ]

    operations = [
        migrations.AddField(
            model_name="loan",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="creditcard",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
    ]
