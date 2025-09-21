from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Acquisition


def _safe_reverse_and_hide(txn, actor=None):
    """Idempotent reverse+hide for a single transaction.

    - No-op when `txn` is None, is a reversal, or already reversed.
    - Creates a hidden reversal row and hides the original.
    - Swaps accounts/entities and amount/destination_amount when both sides exist.
    - Does not raise exceptions (best-effort safety net).
    """
    try:
        if not txn or getattr(txn, "is_reversal", False) or getattr(txn, "is_reversed", False):
            # Ensure original is hidden at least
            if txn and getattr(txn, "is_hidden", False) is False:
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

        rev = Tx.objects.create(
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
        # Mark and hide original
        txn.is_reversed = True
        txn.reversed_at = timezone.now()
        if actor is not None:
            try:
                txn.reversed_by = actor
            except Exception:
                pass
        txn.ledger_status = "reversed"
        txn.is_hidden = True
        txn.save(update_fields=["is_reversed", "reversed_at", "reversed_by", "ledger_status", "is_hidden"])
    except Exception:
        # Swallow any errors: this is a safety net; views/commands handle primary flow
        return


@receiver(post_save, sender=Acquisition)
def enforce_reversal_on_soft_delete(sender, instance: Acquisition, created, **kwargs):
    """When an Acquisition is soft-deleted (is_deleted=True), ensure linked
    transactions are reversed+hidden. This covers cases where deletion occurs
    outside the normal view path or when prior bugs left rows visible.

    Idempotent and best-effort: if already reversed/hidden, does nothing.
    """
    try:
        if getattr(instance, "is_deleted", False):
            # Attempt shared helper when available
            try:
                from transactions.views import _reverse_and_hide as shared_reverse
            except Exception:
                shared_reverse = None

            if instance.purchase_tx_id:
                try:
                    tx = instance.purchase_tx
                    if shared_reverse:
                        shared_reverse(tx, actor=getattr(instance, "user", None))
                    else:
                        _safe_reverse_and_hide(tx, actor=getattr(instance, "user", None))
                except Exception:
                    _safe_reverse_and_hide(getattr(instance, "purchase_tx", None), actor=getattr(instance, "user", None))

            if instance.sell_tx_id:
                try:
                    tx = instance.sell_tx
                    if shared_reverse:
                        shared_reverse(tx, actor=getattr(instance, "user", None))
                    else:
                        _safe_reverse_and_hide(tx, actor=getattr(instance, "user", None))
                except Exception:
                    _safe_reverse_and_hide(getattr(instance, "sell_tx", None), actor=getattr(instance, "user", None))
            # Also reverse the capital-return transaction for this acquisition's sale.
            try:
                from transactions.models import Transaction as Tx
                from decimal import Decimal as _Dec
                cap_amt = (instance.purchase_tx.amount if instance.purchase_tx else _Dec("0")) or _Dec("0")
                caps = Tx.objects.filter(
                    user=instance.user,
                    transaction_type__in=["sell acquisition", "sell_acquisition"],
                    amount=cap_amt,
                    description__icontains=instance.name,
                ).order_by("-date", "-id")
                for cap in caps:
                    if shared_reverse:
                        try:
                            shared_reverse(cap, actor=getattr(instance, "user", None))
                        except Exception:
                            _safe_reverse_and_hide(cap, actor=getattr(instance, "user", None))
                    else:
                        _safe_reverse_and_hide(cap, actor=getattr(instance, "user", None))
            except Exception:
                pass
    except Exception:
        # Never block save; this is a guardrail
        pass
