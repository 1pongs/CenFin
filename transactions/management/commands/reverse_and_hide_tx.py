from django.core.management.base import BaseCommand
from django.db import transaction as dbtx


class Command(BaseCommand):
    help = "Reverse-and-hide one or more transactions by id (comma-separated)."

    def add_arguments(self, parser):
        parser.add_argument("--ids", required=True, help="Comma-separated transaction IDs")

    def handle(self, *args, **opts):
        ids = [s.strip() for s in (opts.get("ids") or "").split(",") if s.strip()]
        if not ids:
            self.stderr.write(self.style.ERROR("No ids provided"))
            return
        try:
            ids = [int(x) for x in ids]
        except ValueError:
            self.stderr.write(self.style.ERROR("IDs must be integers"))
            return

        try:
            from transactions.models import Transaction
            try:
                from transactions.views import _reverse_and_hide as shared_reverse
            except Exception:
                shared_reverse = None

            def _fallback_reverse_and_hide(txn, actor=None):
                if not txn or getattr(txn, "is_reversal", False) or getattr(txn, "is_reversed", False):
                    if txn and getattr(txn, "is_hidden", False) is False:
                        txn.is_hidden = True
                        txn.save(update_fields=["is_hidden"])
                    return
                from transactions.models import Transaction as Tx
                from django.utils import timezone
                has_both = bool(txn.account_source_id and txn.account_destination_id)
                if has_both and txn.destination_amount is not None:
                    amount = txn.destination_amount
                    dest_amount = txn.amount
                else:
                    amount = txn.amount
                    dest_amount = None
                Tx.objects.create(
                    user=txn.user,
                    date=timezone.now().date(),
                    description=f"Reversal of {txn.description}",
                    transaction_type=txn.transaction_type,
                    amount=amount,
                    destination_amount=dest_amount,
                    account_source=txn.account_destination,
                    account_destination=txn.account_source,
                    entity_source=txn.entity_destination,
                    entity_destination=txn.entity_source,
                    currency=txn.currency,
                    is_hidden=True,
                    is_reversal=True,
                    reversed_transaction=txn,
                )
                txn.is_reversed = True
                txn.is_hidden = True
                from django.utils import timezone
                txn.reversed_at = timezone.now()
                txn.ledger_status = "reversed"
                txn.save(update_fields=["is_reversed", "is_hidden", "reversed_at", "ledger_status"])

            for pk in ids:
                t = Transaction.all_objects.filter(pk=pk).first()
                if not t:
                    self.stderr.write(self.style.WARNING(f"Transaction {pk} not found"))
                    continue
                if t.is_reversal:
                    self.stdout.write(self.style.WARNING(f"Transaction {pk} is a reversal; skipping"))
                    continue
                with dbtx.atomic():
                    try:
                        if shared_reverse:
                            shared_reverse(t)
                        else:
                            _fallback_reverse_and_hide(t)
                        self.stdout.write(self.style.SUCCESS(f"Reversed+hid transaction {pk}"))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Failed reversing {pk}: {e}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(str(e)))
