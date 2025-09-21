from django.core.management.base import BaseCommand
from django.db.models import Q
from decimal import Decimal

from cenfin_proj.utils import get_account_entity_balance
from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction


class Command(BaseCommand):
    help = "Debug an account/entity pair balance: print computed total and list contributing transactions (visible, top-level)."

    def add_arguments(self, parser):
        parser.add_argument("--account", required=True, help="Account name (exact match)")
        parser.add_argument("--entity", required=True, help="Entity name (exact match)")
        parser.add_argument("--username", required=False, help="Username to scope lookups")

    def handle(self, *args, **opts):
        username = opts.get("username")
        acc_qs = Account.objects.filter(account_name=opts["account"])  # name is unique per user
        ent_qs = Entity.objects.filter(entity_name=opts["entity"])  # name is unique per user
        if username:
            acc_qs = acc_qs.filter(user__username=username)
            ent_qs = ent_qs.filter(user__username=username)
        acc = acc_qs.first()
        ent = ent_qs.first()
        if not acc or not ent:
            self.stderr.write(self.style.ERROR("Account or Entity not found."))
            return

        total = get_account_entity_balance(acc.id, ent.id, user=acc.user)
        self.stdout.write(self.style.SUCCESS(f"Balance for {ent} / {acc}: {total}"))

        qs = Transaction.objects.filter(
            parent_transfer__isnull=True,
            user=acc.user,
        ).filter(
            Q(entity_destination=ent, account_destination=acc)
            | Q(entity_source=ent, account_source=acc)
        )
        rows = []
        for t in qs.order_by("date", "id"):
            # sign: + for dest liquid, - for src liquid; ignore non-liquid at this layer
            sign = Decimal("0")
            amt = Decimal("0")
            side = ""
            if (
                t.entity_destination_id == ent.id
                and t.account_destination_id == acc.id
                and (t.asset_type_destination or "").lower() == "liquid"
            ):
                side = "+dest"
                amt = t.destination_amount if t.destination_amount is not None else t.amount
                sign = Decimal("1")
            if (
                t.entity_source_id == ent.id
                and t.account_source_id == acc.id
                and (t.asset_type_source or "").lower() == "liquid"
            ):
                side = "-src"
                amt = t.amount
                sign = Decimal("-1")
            rows.append(
                f"{t.date} {t.id} {side:>5} {t.transaction_type:>16} {t.description or ''}  amt={amt} hidden={t.is_hidden} reversal={t.is_reversal}"
            )
        self.stdout.write("\nTransactions contributing to the pair balance (visible, top-level):")
        for r in rows:
            self.stdout.write(r)
