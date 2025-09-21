from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from acquisitions.models import Acquisition
from transactions.models import Transaction


def _local_reverse_and_hide(txn, actor=None):
    """Minimal, idempotent reverse+hide for a single visible root txn.

    - Creates a hidden reversal row with swapped sides.
    - Marks original as reversed and hidden.
    - No-op if txn already reversed or is a reversal.
    """
    if not txn or getattr(txn, "is_reversal", False) or getattr(txn, "is_reversed", False):
        # Still ensure it's hidden if the acquisition was deleted
        if getattr(txn, "is_hidden", False) is False:
            txn.is_hidden = True
            txn.save(update_fields=["is_hidden"])
        return
    from transactions.models import Transaction as Tx

    has_both = bool(txn.account_source_id and txn.account_destination_id)
    if has_both and txn.destination_amount is not None:
        amount = txn.destination_amount
        dest_amount = txn.amount
    else:
        amount = txn.amount
        dest_amount = None
    # reversal row (hidden)
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
    txn.reversed_at = timezone.now()
    if actor is not None:
        txn.reversed_by = actor
    txn.ledger_status = "reversed"
    txn.is_hidden = True
    txn.save(update_fields=["is_reversed", "reversed_at", "reversed_by", "ledger_status", "is_hidden"])


class Command(BaseCommand):
    help = "Repair archived acquisitions by reversing/hiding their linked transactions if missing."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Limit repair to a specific username", default=None)

    def handle(self, *args, **options):
        username = options.get("username")
        user = None
        if username:
            User = get_user_model()
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"User not found: {username}"))
                return

        qs = Acquisition.objects.filter(is_deleted=True)
        if user:
            qs = qs.filter(user=user)

        repaired = 0
        checked = 0
        try:
            from transactions.views import _reverse_and_hide as shared_reverse
        except Exception:
            shared_reverse = None

        for acq in qs.iterator():
            checked += 1
            changed = False
            with transaction.atomic():
                # Try to resolve a missing purchase_tx by heuristics: find a
                # visible, non-reversed 'buy acquisition' row matching the
                # acquisition name. If exactly one candidate exists, treat it as
                # the purchase and link it to the acquisition for future safety.
                if not acq.purchase_tx_id:
                    try:
                        cands = list(
                            Transaction.objects.filter(
                                user=acq.user,
                                transaction_type="buy acquisition",
                                description__icontains=(acq.name or ""),
                                is_reversal=False,
                            ).order_by("-date")
                        )
                        if len(cands) == 1:
                            acq.purchase_tx = cands[0]
                            acq.save(update_fields=["purchase_tx"])
                    except Exception:
                        pass

                if acq.purchase_tx_id:
                    pt = acq.purchase_tx
                    if pt and (not getattr(pt, "is_hidden", False) or not getattr(pt, "is_reversed", False)):
                        try:
                            if shared_reverse:
                                shared_reverse(pt, actor=acq.user)
                            else:
                                _local_reverse_and_hide(pt, actor=acq.user)
                        except Exception:
                            _local_reverse_and_hide(pt, actor=acq.user)
                        changed = True
                if acq.sell_tx_id:
                    st = acq.sell_tx
                    if st and (not getattr(st, "is_hidden", False) or not getattr(st, "is_reversed", False)):
                        try:
                            if shared_reverse:
                                shared_reverse(st, actor=acq.user)
                            else:
                                _local_reverse_and_hide(st, actor=acq.user)
                        except Exception:
                            _local_reverse_and_hide(st, actor=acq.user)
                        changed = True
            if changed:
                repaired += 1

        self.stdout.write(self.style.SUCCESS(
            f"Checked {checked} archived acquisitions; repaired {repaired}."
        ))
