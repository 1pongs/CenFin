from django.db import migrations


def create_default_outside_entity(apps, schema_editor):
    Entity = apps.get_model('entities', 'Entity')
    Entity.objects.get_or_create(
        entity_name='Outside',
        entity_type='outside',
        user=None,
    )

class Migration(migrations.Migration):

    dependencies = [
        ('entities', '0004_entity_is_visible'),
    ]

    operations = [
        migrations.RunPython(create_default_outside_entity, migrations.RunPython.noop),
    ]