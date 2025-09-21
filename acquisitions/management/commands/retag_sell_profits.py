from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from acquisitions.models import Acquisition
from transactions.models import Transaction


class Command(BaseCommand):
    help = (
        "Dry-run / apply: convert Acquisition sale profit transactions to 'income' "
        "and ensure capital-return transactions use 'sell_acquisition'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes (default is dry-run).",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="If provided, restrict to acquisitions owned by this username.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit number of acquisitions processed (0 = no limit).",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        username = options.get("user")
        limit = options.get("limit") or None

        qs = Acquisition.objects.filter(sell_tx__isnull=False)
        if username:
            User = get_user_model()
            try:
                u = User.objects.get(username=username)
                qs = qs.filter(user=u)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User {username!r} not found."))
                return

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"Found {total} acquisitions with a recorded sell_tx")

        changed = 0
        created_capital = 0
        with transaction.atomic():
            for acq in qs:
                buy_tx = acq.purchase_tx
                profit_tx = acq.sell_tx
                if not profit_tx:
                    continue

                capital_cost = buy_tx.amount if buy_tx else None

                # Ensure profit tx is 'income'
                if profit_tx.transaction_type != "income":
                    self.stdout.write(
                        f"Acq {acq.pk}: profit tx {profit_tx.pk} will be changed {profit_tx.transaction_type!r} -> 'income'"
                    )
                    if apply_changes:
                        profit_tx.transaction_type = "income"
                        profit_tx.full_clean()
                        profit_tx.save()
                        changed += 1

                # Find candidate capital return transaction: prefer same amount (capital_cost)
                capital_tx = None
                if capital_cost is not None:
                    capital_tx = (
                        Transaction.objects.filter(
                            user=acq.user,
                            amount=capital_cost,
                            description__icontains=acq.name,
                        )
                        .exclude(pk=profit_tx.pk)
                        .order_by("-date")
                        .first()
                    )

                if capital_tx:
                    if capital_tx.transaction_type not in (
                        "sell acquisition",
                        "sell_acquisition",
                    ):
                        self.stdout.write(
                            f"Acq {acq.pk}: capital tx {capital_tx.pk} will be changed {capital_tx.transaction_type!r} -> 'sell acquisition'"
                        )
                        if apply_changes:
                            capital_tx.transaction_type = "sell acquisition"
                            capital_tx.full_clean()
                            capital_tx.save()
                            changed += 1
                else:
                    self.stdout.write(
                        f"Acq {acq.pk}: no capital return tx found (capital_cost={capital_cost})"
                    )
                    if apply_changes and capital_cost is not None:
                        # Create a capital return record to preserve pairing
                        self.stdout.write(
                            f"Acq {acq.pk}: creating capital return transaction (sell acquisition)"
                        )
                        Transaction.objects.create(
                            user=acq.user,
                            date=profit_tx.date,
                            description=f"Sell {acq.name} \u2014 capital return",
                            transaction_type="sell acquisition",
                            amount=capital_cost,
                            currency=getattr(buy_tx, "currency", None),
                            account_source=profit_tx.account_source,
                            account_destination=profit_tx.account_destination,
                            entity_source=profit_tx.entity_source,
                            entity_destination=profit_tx.entity_destination,
                            remarks=profit_tx.remarks,
                        )
                        created_capital += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Dry-run complete."
                if not apply_changes
                else f"Applied changes: {changed} updates, {created_capital} capital returns created."
            )
        )
