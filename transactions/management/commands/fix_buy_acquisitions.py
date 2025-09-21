from django.core.management.base import BaseCommand
from django.db.models import Q

from transactions.models import Transaction


class Command(BaseCommand):
    help = (
        "Reclassify eligible Outside transfers as 'buy acquisition' so they "
        "increase non-liquid (Asset) for the destination entity and reduce Liquid."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Only report, do not write changes"
        )
        parser.add_argument(
            "--user-id", type=int, default=None, help="Limit to a specific user id"
        )

    def handle(self, *args, **options):
        dry = options.get("dry_run")
        user_id = options.get("user_id")

        q = Q(parent_transfer__isnull=True, is_reversal=False)
        if user_id:
            q &= Q(user_id=user_id)

        # Destination account is Outside; current type looks like a liquid transfer
        qs = (
            Transaction.all_objects.filter(q)
            .filter(
                Q(transaction_type__iexact="transfer")
                | Q(transaction_type__isnull=True)
            )
            .select_related("account_destination", "entity_destination")
        )

        def is_outside_account(acc):
            return bool(
                acc
                and (
                    getattr(acc, "account_type", None) == "Outside"
                    or getattr(acc, "account_name", None) == "Outside"
                )
            )

        updated = 0
        scanned = 0
        for t in qs:
            scanned += 1
            if not is_outside_account(getattr(t, "account_destination", None)):
                continue
            # Must point to a concrete destination entity (not Outside)
            if not t.entity_destination_id:
                continue
            ent_name = (
                getattr(getattr(t, "entity_destination", None), "entity_name", "") or ""
            )
            if ent_name.lower() == "outside":
                continue

            # Reclassify
            self.stdout.write(
                f"Reclassify tx #{t.id} -> buy acquisition (dest entity: {ent_name})"
            )
            if not dry:
                t.transaction_type = "buy acquisition"
                # Populate dependent fields to ensure asset/liquid flags are correct
                t._apply_defaults()
                t.save(
                    update_fields=[
                        "transaction_type",
                        "transaction_type_source",
                        "transaction_type_destination",
                        "asset_type_source",
                        "asset_type_destination",
                    ]
                )
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Scanned: {scanned}; Updated: {updated}"))
