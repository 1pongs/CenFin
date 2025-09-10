from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acquisitions", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Database already contains this column in some environments;
            # update Django state only to avoid duplicate ADD COLUMN.
            state_operations=[
                migrations.AddField(
                    model_name="acquisition",
                    name="provider",
                    field=models.CharField(max_length=255, blank=True, null=True, default=None),
                ),
            ],
            database_operations=[],
        ),
    ]
