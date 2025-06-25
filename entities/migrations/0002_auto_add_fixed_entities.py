from django.db import migrations

def create_fixed_entities(apps, schema_editor):
    from entities.utils import ensure_fixed_entities
    from accounts.utils import ensure_outside_account
    ensure_fixed_entities()
    ensure_outside_account()

class Migration(migrations.Migration):
    dependencies = [
        ('entities', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_fixed_entities, migrations.RunPython.noop),
    ]
