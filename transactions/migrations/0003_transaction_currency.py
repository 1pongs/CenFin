# Generated by Django 5.2 on 2025-07-13 10:38

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('currencies', '0003_alter_exchangerate_source'),
        ('transactions', '0002_alter_categorytag_transaction_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='currency',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='currencies.currency'),
        ),
    ]
