from django.db import migrations


def forwards(apps, schema_editor):
    Transaction = apps.get_model('transactions', 'Transaction')
    for tx in Transaction.objects.filter(currency__isnull=True):
        if tx.transaction_type == 'expense' and tx.account_source_id:
            account = tx.account_source
        else:
            account = tx.account_destination if tx.account_destination_id else tx.account_source
        if account and getattr(account, 'currency_id', None):
            Transaction.objects.filter(pk=tx.pk).update(currency_id=account.currency_id)


def backwards(apps, schema_editor):
    Transaction = apps.get_model('transactions', 'Transaction')
    Transaction.objects.filter(currency__isnull=False).update(currency=None)


class Migration(migrations.Migration):
    dependencies = [
        ('transactions', '0005_transaction_destination_amount'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]