# Generated by Django 5.2 on 2025-06-19 21:05

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Insurance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('insurance_type', models.CharField(choices=[('term', 'Term'), ('whole', 'Whole'), ('health', 'Health'), ('vul', 'VUL')], max_length=10)),
                ('sum_assured', models.DecimalField(decimal_places=2, max_digits=18)),
                ('premium_mode', models.CharField(choices=[('annual', 'Annual'), ('semiannual', 'Semi-Annual'), ('quarterly', 'Quarterly'), ('monthly', 'Monthly')], max_length=20)),
                ('premium_amount', models.DecimalField(decimal_places=2, max_digits=18)),
                ('unit_balance', models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ('unit_value', models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ('valuation_date', models.DateField(blank=True, null=True)),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='insurances', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'insurance_insurance',
            },
        ),
        migrations.CreateModel(
            name='PremiumPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('amount', models.DecimalField(decimal_places=2, max_digits=18)),
                ('note', models.CharField(blank=True, max_length=255)),
                ('insurance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='premiums', to='insurance.insurance')),
            ],
            options={
                'db_table': 'insurance_premiumpayment',
            },
        ),
    ]
