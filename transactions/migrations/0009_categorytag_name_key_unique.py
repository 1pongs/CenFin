from django.db import migrations, models


def _normalize(value: str) -> str:
    if not value:
        return ""
    v = " ".join((value or "").strip().lower().split())
    if len(v) > 4 and v.endswith("s") and not v.endswith("ss"):
        v = v[:-1]
    import re as _re
    v = _re.sub(r"[^a-z0-9]+", "", v)
    return v


def populate_name_keys(apps, schema_editor):
    CategoryTag = apps.get_model('transactions', 'CategoryTag')
    Transaction = apps.get_model('transactions', 'Transaction')
    # 1) Fill name_key
    for tag in CategoryTag.objects.all().iterator():
        key = _normalize(tag.name)
        if tag.name_key != key:
            tag.name_key = key
            tag.save(update_fields=["name_key"])

    # 2) Merge duplicates by normalized key within scope
    from collections import defaultdict
    buckets = defaultdict(list)
    for tag in CategoryTag.objects.all():
        buckets[(tag.user_id, tag.transaction_type, tag.entity_id, tag.name_key)].append(tag)

    for (_user, _ttype, _ent, _key), tags in buckets.items():
        if len(tags) <= 1:
            continue
        # Keep the earliest (smallest id) as canonical
        tags.sort(key=lambda t: t.id)
        canonical = tags[0]
        for dup in tags[1:]:
            # Reattach M2M relationships to the canonical tag
            for tx in dup.transactions.all():
                canonical.transactions.add(tx)
            dup.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0008_alter_categorytag_unique_together_categorytag_entity_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='categorytag',
            name='name_key',
            field=models.CharField(db_index=True, default='', editable=False, max_length=80),
        ),
        migrations.RunPython(populate_name_keys, reverse_code=migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='categorytag',
            unique_together={('user', 'transaction_type', 'name_key', 'entity')},
        ),
    ]

