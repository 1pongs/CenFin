from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acquisitions", "0004_merge"),
    ]

    operations = [
        migrations.AddField(
            model_name="acquisition",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
    ]

