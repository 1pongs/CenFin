from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0010_hide_old_reversals"),
        ("transactions", "0009_categorytag_name_key_unique"),
    ]

    operations = []
