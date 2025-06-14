from django.db import migrations


def create_default_outside_account(apps, schema_editor):
    Account = apps.get_model('accounts', 'Account')
    Account.objects.get_or_create(
        account_name='Outside',
        account_type='Outside',
        user=None,
    )

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_account_is_visible_alter_account_account_type'),
    ]

    operations = [
        migrations.RunPython(create_default_outside_account, migrations.RunPython.noop),
    ]