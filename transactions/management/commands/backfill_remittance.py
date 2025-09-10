from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from transactions.models import Transaction
from accounts.utils import ensure_remittance_account
from entities.utils import ensure_remittance_entity


class Command(BaseCommand):
    help = (
        "Ensure a single Remittance entity/account per user and backfill "
        "existing cross-currency child transfer legs to reference them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write changes; print what would be changed.",
        )

    def handle(self, *args, **options):
        dry = options.get("dry_run", False)
        User = get_user_model()

        created_users = 0
        updated_txs = 0

        # 1) Ensure Remittance entity/account exist for all users
        for user in User.objects.all():
            rem_ent = ensure_remittance_entity(user)
            rem_acc = ensure_remittance_account(user)
            if rem_ent and rem_acc:
                created_users += 1

        # 2) Backfill hidden child legs with missing account/entity fields
        q_missing = (
            Q(account_source_id__isnull=True)
            | Q(account_destination_id__isnull=True)
            | Q(entity_source_id__isnull=True)
            | Q(entity_destination_id__isnull=True)
        )

        qs = (
            Transaction.all_objects
            .filter(parent_transfer__isnull=False, is_hidden=True)
            .filter(q_missing)
            .select_related("user")
        )

        self.stdout.write(f"Scanning {qs.count()} child legs with missing refs…")

        with transaction.atomic():
            for tx in qs.iterator():
                user = tx.user
                if user is None:
                    # Skip orphaned rows
                    continue
                rem_ent = ensure_remittance_entity(user)
                rem_acc = ensure_remittance_account(user)

                fields = []
                if tx.account_source_id is None:
                    tx.account_source = rem_acc
                    fields.append("account_source")
                if tx.account_destination_id is None:
                    tx.account_destination = rem_acc
                    fields.append("account_destination")
                if tx.entity_source_id is None:
                    tx.entity_source = rem_ent
                    fields.append("entity_source")
                if tx.entity_destination_id is None:
                    tx.entity_destination = rem_ent
                    fields.append("entity_destination")

                if fields:
                    updated_txs += 1
                    if not dry:
                        tx.save(update_fields=fields)

            if dry:
                # Roll back any side-effects if dry run
                raise transaction.TransactionManagementError("Dry run - rollback")

        self.stdout.write(self.style.SUCCESS(
            f"Ensured Remittance for {created_users} users; backfilled {updated_txs} transactions."
        ))

