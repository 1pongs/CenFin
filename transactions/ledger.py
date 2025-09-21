from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
from django.utils import timezone
from django.db import transaction as db_transaction
from django.db.models import Q, Max

from .models import Transaction


@dataclass
class LedgerBlocker:
    account_id: int
    newer: List[dict]


def _unit_members(unit: Transaction) -> List[Transaction]:
    """Return the transaction(s) composing a unit.

    A unit is either a single transaction or a pair linked by ``group_id``.
    """
    if unit.group_id:
        return list(
            Transaction.all_objects.filter(group_id=unit.group_id, is_deleted=False)
        )
    return [unit]


def check_lifo_allowed(unit: Transaction) -> Tuple[bool, List[LedgerBlocker]]:
    members = _unit_members(unit)
    blockers: List[LedgerBlocker] = []
    for t in members:
        accounts = {t.account_source_id, t.account_destination_id}
        accounts.discard(None)
        for acc_id in accounts:
            last_seq = (
                Transaction.all_objects.filter(
                    Q(account_source_id=acc_id) | Q(account_destination_id=acc_id),
                    is_deleted=False,
                ).aggregate(Max("seq_account"))["seq_account__max"]
                or 0
            )
            if t.seq_account != last_seq:
                newer = Transaction.all_objects.filter(
                    Q(account_source_id=acc_id) | Q(account_destination_id=acc_id),
                    is_deleted=False,
                    seq_account__gt=t.seq_account,
                ).order_by("-seq_account")[:5]
                blockers.append(
                    LedgerBlocker(
                        account_id=acc_id,
                        newer=list(newer.values("id", "seq_account", "description")),
                    )
                )
    return (len(blockers) == 0, blockers)


def reverse_unit(unit: Transaction, actor, reverse_date=None) -> List[Transaction]:
    if unit.transaction_type in {"income", "loan_disbursement"}:
        raise ValueError("ReversalNotApplicable")

    reverse_date = reverse_date or timezone.now().date()
    members = _unit_members(unit)
    reversals: List[Transaction] = []
    with db_transaction.atomic():
        for t in members:
            rev = Transaction.objects.create(
                user=t.user,
                date=reverse_date,
                description=f"Reversal of {t.id}",
                transaction_type=t.transaction_type,
                amount=-t.amount if t.amount else None,
                account_source=t.account_source,
                account_destination=t.account_destination,
                currency=t.currency,
                group_id=t.group_id,
                is_reversal=True,
                reversed_transaction=t,
            )
            reversals.append(rev)
            t.is_reversed = True
            t.reversed_at = timezone.now()
            t.reversed_by = actor
            t.ledger_status = "reversed"
            t.save(
                update_fields=[
                    "is_reversed",
                    "reversed_at",
                    "reversed_by",
                    "ledger_status",
                ]
            )
    return reversals


def delete_unit(unit: Transaction, mode: str, actor) -> List[Transaction]:
    if unit.is_deleted:
        raise ValueError("Already deleted")
    if unit.is_reversed and mode == "reverse_delete_unit":
        raise ValueError("Already reversed")

    ok, blockers = check_lifo_allowed(unit)
    if not ok:
        raise ValueError({"blockers": [b.__dict__ for b in blockers]})

    members = _unit_members(unit)
    reversals: List[Transaction] = []
    with db_transaction.atomic():
        if mode == "reverse_delete_unit" and unit.transaction_type not in {
            "income",
            "loan_disbursement",
        }:
            for m in members:
                reversals.extend(reverse_unit(m, actor))
        for m in members:
            m.is_deleted = True
            m.deleted_at = timezone.now()
            m.deleted_by = actor
            m.ledger_status = "deleted"
            m.save(
                update_fields=[
                    "is_deleted",
                    "deleted_at",
                    "deleted_by",
                    "ledger_status",
                ]
            )
    return reversals
