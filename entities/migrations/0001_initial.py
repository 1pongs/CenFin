# Generated by Django 5.2 on 2025-05-06 09:58

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Entity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entity_name', models.CharField(max_length=100)),
                ('entity_type', models.CharField(choices=[('Account', 'Account'), ('Investment', 'Investment'), ('Emergency Fund', 'Emergency Fund'), ('Business Fund', 'Business Fund'), ('Retirement Fund', 'Retirement Fund'), ('Educational Fund', 'Educational Fund'), ('Outside', 'Outside')], max_length=50)),
                ('is_active', models.BooleanField(default=True)),
            ],
        ),
    ]
