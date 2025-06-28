from django.db import migrations


def set_account_flag(apps, schema_editor):
    Entity = apps.get_model('entities', 'Entity')
    Entity.objects.filter(entity_name='Account').update(is_account_entity=True)


class Migration(migrations.Migration):

    dependencies = [
        ('entities', '0003_entity_is_account_entity'),
    ]

    operations = [
        migrations.RunPython(set_account_flag, migrations.RunPython.noop),
    ]