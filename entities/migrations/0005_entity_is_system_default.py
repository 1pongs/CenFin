# Generated by Django 5.2 on 2025-06-28 08:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('entities', '0004_set_account_entity_flag'),
    ]

    operations = [
        migrations.AddField(
            model_name='entity',
            name='is_system_default',
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
