from django.core.management.base import BaseCommand
from django.conf import settings
from decimal import Decimal

from entities.models import Entity
from transactions.models import Transaction
from django.db import models
from acquisitions.models import Acquisition
from cenfin_proj.utils import get_entity_liquid_nonliquid_totals


class Command(BaseCommand):
    help = (
        "Dump transactions and computed non-liquid total for an entity by name or id."
    )

    def add_arguments(self, parser):
        parser.add_argument("--name", "-n", help="Entity name (case-insensitive)")
        parser.add_argument("--id", "-i", type=int, help="Entity primary key")
        parser.add_argument(
            "--user", "-u", help="Username (optional) to filter entities"
        )
        parser.add_argument(
            "--currency", "-c", help="Display currency code (defaults to BASE_CURRENCY)"
        )

    def handle(self, *args, **options):
        name = options.get("name")
        ent_id = options.get("id")
        username = options.get("user")
        disp_code = options.get("currency") or getattr(settings, "BASE_CURRENCY", "PHP")

        qs = Entity.objects.all()
        if ent_id:
            qs = qs.filter(pk=ent_id)
        elif name:
            qs = qs.filter(entity_name__iexact=name)
        if username:
            qs = qs.filter(user__username=username)

        if not qs.exists():
            self.stdout.write(self.style.ERROR("No matching entities found"))
            return

        for ent in qs:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f'Entity: {ent} (pk={ent.pk}) user={getattr(ent.user, "username", None)}'
                )
            )
            totals = get_entity_liquid_nonliquid_totals(ent.user, disp_code)
            t = totals.get(ent.pk, {"liquid": Decimal("0"), "non_liquid": Decimal("0")})
            self.stdout.write(
                f'Computed (display currency={disp_code}) -> liquid: {t["liquid"]}  non_liquid: {t["non_liquid"]}\n'
            )

            # Show contributing transactions (top-level only)
            txs = (
                Transaction.objects.filter(user=ent.user, parent_transfer__isnull=True)
                .filter(models.Q(entity_source=ent) | models.Q(entity_destination=ent))
                .select_related(
                    "currency",
                    "account_source",
                    "account_destination",
                    "account_destination__currency",
                )
                .order_by("date")
            )

            if not txs.exists():
                self.stdout.write("  No top-level transactions for this entity\n")
                continue

            for tx in txs:
                try:
                    _dest_amt = (
                        tx.destination_amount
                        if tx.destination_amount is not None
                        else tx.amount
                    )
                except Exception:
                    _ = tx.amount
                src_outside = bool(
                    tx.account_source
                    and (
                        getattr(tx.account_source, "account_type", None) == "Outside"
                        or getattr(tx.account_source, "account_name", None) == "Outside"
                    )
                )
                dest_outside = bool(
                    tx.account_destination
                    and (
                        getattr(tx.account_destination, "account_type", None)
                        == "Outside"
                        or getattr(tx.account_destination, "account_name", None)
                        == "Outside"
                    )
                )
                line = (
                    f"id={tx.pk} date={tx.date} type={tx.transaction_type} "
                    f"asset_src={tx.asset_type_source} asset_dst={tx.asset_type_destination} "
                    f"src_ent={getattr(tx.entity_source, 'entity_name', None)} dst_ent={getattr(tx.entity_destination, 'entity_name', None)} "
                    f"amount={tx.amount} dest_amount={tx.destination_amount} cur={getattr(tx.currency, 'code', None)} "
                    f"acc_src={getattr(tx.account_source, 'account_name', None)} acc_dst={getattr(tx.account_destination, 'account_name', None)} "
                    f"src_outside={src_outside} dest_outside={dest_outside}"
                )
                self.stdout.write("  " + line)

            # Show acquisitions tied to this entity
            acqs = Acquisition.objects.filter(
                user=ent.user, purchase_tx__entity_destination=ent
            )
            if acqs.exists():
                self.stdout.write(self.style.MIGRATE_LABEL("  Acquisitions:"))
                for a in acqs:
                    pur = a.purchase_tx
                    sell = a.sell_tx
                    self.stdout.write(
                        f"    id={a.pk} name={a.name} purchase_tx={getattr(pur, 'pk', None)} amount={getattr(pur, 'amount', None)} sell_tx={getattr(sell, 'pk', None)} sell_amount={getattr(sell, 'amount', None)}"
                    )
            else:
                self.stdout.write("  No acquisitions linked to this entity")

            self.stdout.write("")
