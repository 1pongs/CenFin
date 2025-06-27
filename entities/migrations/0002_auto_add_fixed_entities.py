from django.db import migrations

def create_fixed_entities(apps, schema_editor):
    # No-op placeholder; default entities are created via user signals.
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('entities', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_fixed_entities, migrations.RunPython.noop),
    ]
