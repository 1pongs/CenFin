# Generated by Django 5.2 on 2025-07-10 09:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_base_currency_user_preferred_rate_source'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='preferred_rate_source',
            field=models.CharField(choices=[('USER', 'User-defined'), ('FRANKFURTER', 'Frankfurter'), ('REM_A', 'Remittance Center A')], default='FRANKFURTER', max_length=20),
        ),
    ]
