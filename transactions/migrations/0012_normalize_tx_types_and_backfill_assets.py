from django.db import migrations
from django.db.models import Q

TX_MAP = {
    "buy acquisition": ("transfer", "buy_acquisition", "liquid", "non_liquid"),
    "sell acquisition": ("buy_acquisition", "transfer", "non_liquid", "liquid"),
}


def normalize_and_backfill(apps, schema_editor):
    Transaction = apps.get_model("transactions", "Transaction")

    # 1) Normalize underscore variants to space-separated for consistency
    underscore_to_space = {
        "buy_acquisition": "buy acquisition",
        "sell_acquisition": "sell acquisition",
    }
    for old, new in underscore_to_space.items():
        Transaction.objects.filter(transaction_type=old).update(transaction_type=new)

    # 2) Backfill dependent mapping fields for acquisition rows and for any rows
    # missing asset_type_source/destination to keep future filters reliable
    missing = Q(asset_type_source__isnull=True) | Q(asset_type_destination__isnull=True)
    acq_types = Q(transaction_type__in=["buy acquisition", "sell acquisition"]) | Q(
        transaction_type__in=["buy_acquisition", "sell_acquisition"]
    )

    qs = Transaction.objects.filter(acq_types | missing)
    # Iterate in chunks to avoid large transactions in big datasets
    BATCH = 500
    start = 0
    while True:
        batch = list(qs.order_by("id")[start : start + BATCH].values(
            "id",
            "transaction_type",
            "transaction_type_source",
            "transaction_type_destination",
            "asset_type_source",
            "asset_type_destination",
        ))
        if not batch:
            break
        updates = []
        for row in batch:
            ttype = (row["transaction_type"] or "").replace("_", " ")
            mapping = TX_MAP.get(ttype)
            if not mapping:
                continue
            tsrc, tdest, asrc, adest = mapping
            need = False
            if not row.get("transaction_type_source") or row["transaction_type_source"] != tsrc:
                need = True
            if not row.get("transaction_type_destination") or row["transaction_type_destination"] != tdest:
                need = True
            if not row.get("asset_type_source") or row["asset_type_source"] != asrc:
                need = True
            if not row.get("asset_type_destination") or row["asset_type_destination"] != adest:
                need = True
            if need:
                updates.append(
                    Transaction(
                        id=row["id"],
                        transaction_type=ttype,
                        transaction_type_source=tsrc,
                        transaction_type_destination=tdest,
                        asset_type_source=asrc,
                        asset_type_destination=adest,
                    )
                )
        if updates:
            Transaction.objects.bulk_update(
                updates,
                [
                    "transaction_type",
                    "transaction_type_source",
                    "transaction_type_destination",
                    "asset_type_source",
                    "asset_type_destination",
                ],
                batch_size=BATCH,
            )
        start += BATCH


def noop_reverse(apps, schema_editor):
    # No data rollback; safe to re-run forward if needed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0011_merge_conflict_categorykey_and_hide_old"),
    ]

    operations = [
        migrations.RunPython(normalize_and_backfill, noop_reverse),
    ]
