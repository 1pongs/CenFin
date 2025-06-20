# Generated by Django 5.2 on 2025-05-25 21:44

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0003_transaction_transaction_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='transactions.transactiontemplate'),
        ),
        migrations.AlterField(
            model_name='transactiontemplate',
            name='autopop_map',
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='transactiontemplate',
            name='name',
            field=models.CharField(max_length=60, unique=True),
        ),
    ]
