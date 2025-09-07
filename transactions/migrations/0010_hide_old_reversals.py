from django.db import migrations


def hide_old_reversals(apps, schema_editor):
    Transaction = apps.get_model('transactions', 'Transaction')
    # Mark legacy reversal entries (created before is_reversal flag) as hidden
    # and set the is_reversal flag for consistency.
    qs = Transaction.objects.filter(description__istartswith='reversal of').exclude(is_reversal=True)
    for t in qs.iterator():
        t.is_reversal = True
        t.is_hidden = True
        t.save(update_fields=["is_reversal", "is_hidden"])


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0009_transaction_deleted_at_transaction_deleted_by_and_more'),
    ]

    operations = [
        migrations.RunPython(hide_old_reversals, migrations.RunPython.noop),
    ]

