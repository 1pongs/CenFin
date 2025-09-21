from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("acquisitions", "0002_add_provider_field"),
        ("acquisitions", "0003_drop_legacy_insurance_type"),
    ]

    operations = []
