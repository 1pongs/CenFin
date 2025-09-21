from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction as db_tx
from django.db.models import Case, DecimalField, F, Q, Sum, When
from django.utils import timezone

from .models import Transaction
from accounts.models import Account
from .constants import transaction_type_TX_MAP




@dataclass
class NegativeBalanceHit:
    account_id: int
    date: Optional[object]
    balance: Decimal
    # Optional: entity id associated with the transaction that triggered the hit
    entity_id: Optional[int] = None


def _amount_inflow_expr():
    """Expression to represent inflow amount (destination side prefers destination_amount)."""
    return Case(
        When(destination_amount__isnull=False, then=F("destination_amount")),
        default=F("amount"),
        output_field=DecimalField(),
    )


def _balance_before(account_id: int, user_id: int, start_date) -> Decimal:
    """Compute account balance strictly before start_date using visible (posted) rows.

    Rules mirror Account.with_current_balance():
    - Only visible, non-deleted, non-reversal rows
    - Parent transfers are included (child transfers are hidden), so just rely on default manager
    - Inflow uses destination_amount when present, else amount
    - Outflow uses amount on source side
    """
    inflow = (
        Transaction.objects.filter(
            user_id=user_id,
            account_destination_id=account_id,
            date__lt=start_date,
        )
        .annotate(adj_amount=_amount_inflow_expr())
        .aggregate(total=Sum("adj_amount"))
        .get("total")
        or Decimal("0")
    )
    outflow = (
        Transaction.objects.filter(
            user_id=user_id,
            account_source_id=account_id,
            date__lt=start_date,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )
    return Decimal(str(inflow)) - Decimal(str(outflow))


def _stream_after(
    account_id: int,
    user_id: int,
    start_date,
    excluded_ids: Sequence[int],
    for_update: bool = False,
) -> List[Transaction]:
    """Return visible transactions affecting account_id on/after start_date, excluding ids.

    Ordered by date, posted_at, id to maintain stable processing sequence.
    """
    qs = (
        Transaction.objects.filter(
            user_id=user_id,
            date__gte=start_date,
        )
        .filter(Q(account_source_id=account_id) | Q(account_destination_id=account_id))
        .exclude(pk__in=list(excluded_ids) if excluded_ids else [])
        .order_by("date", "posted_at", "id")
    )
    if for_update:
        qs = qs.select_for_update()
    return list(qs)


def _delta_for_account(tx: Transaction, account_id: int) -> Decimal:
    """Compute the signed effect of a transaction on a specific account.

    - Inflow when the account is the destination: +destination_amount or +amount
    - Outflow when the account is the source: -amount
    If a single transaction hits both sides with the same account, both rules apply
    in sequence (net zero in normal single-leg cases but consistent with our balance
    computation rules).
    """
    delta = Decimal("0")
    if tx.account_destination_id == account_id:
        val = tx.destination_amount if tx.destination_amount is not None else tx.amount
        delta += Decimal(str(val or 0))
    if tx.account_source_id == account_id:
        delta -= Decimal(str(tx.amount or 0))
    return delta


# ---------------- Entity-level optional cover helpers ----------------
def _entity_balance_before(entity_id: int, user_id: int, start_date) -> Decimal:
    """Compute the entity's liquid balance strictly before start_date using
    visible (posted) rows. Mirrors get_entity_balance() but with a date filter
    and skipping transfers to/from Outside for liquid classification.
    """
    from .models import Transaction as Tx

    running = Decimal("0")
    qs = (
        Tx.objects.filter(user_id=user_id, date__lt=start_date)
        .filter(Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id))
        .select_related("account_source", "account_destination")
        .order_by("date", "posted_at", "id")
    )

    for t in qs:
        ttype = (getattr(t, "transaction_type", "") or "").lower()
        # Inflow to entity (destination side, liquid), excluding transfers to Outside
        if (
            t.entity_destination_id == entity_id
            and (getattr(t, "asset_type_destination", "") or "").lower() == "liquid"
        ):
            dest_outside = _is_outside_account(getattr(t, "account_destination_id", None))
            if not (ttype == "transfer" and dest_outside):
                val = t.destination_amount if t.destination_amount is not None else t.amount
                running += Decimal(str(val or 0))
        # Outflow from entity (source side, liquid), excluding transfers from Outside
        if (
            t.entity_source_id == entity_id
            and (getattr(t, "asset_type_source", "") or "").lower() == "liquid"
        ):
            src_outside = _is_outside_account(getattr(t, "account_source_id", None))
            if not (ttype == "transfer" and src_outside):
                running -= Decimal(str(getattr(t, "amount", None) or 0))

    return running


def _entity_stream_after(
    entity_id: int,
    user_id: int,
    start_date,
    excluded_ids: Sequence[int],
    for_update: bool = False,
) -> List[Transaction]:
    from .models import Transaction as Tx

    qs = (
        Tx.objects.filter(user_id=user_id, date__gte=start_date)
        .filter(Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id))
        .exclude(pk__in=list(excluded_ids) if excluded_ids else [])
        .select_related("account_source", "account_destination")
        .order_by("date", "posted_at", "id")
    )
    if for_update:
        qs = qs.select_for_update()
    return list(qs)


def _delta_for_entity(tx: Transaction, entity_id: int) -> Decimal:
    """Signed liquid effect of a transaction for a specific entity, with
    Outside transfer rules similar to entity balance helpers.
    """
    ttype = (getattr(tx, "transaction_type", "") or "").lower()
    delta = Decimal("0")
    if tx.entity_destination_id == entity_id:
        dest_outside = _is_outside_account(getattr(tx, "account_destination_id", None))
        # Determine asset classes with fallback to constants map
        try:
            tx_key = ((getattr(tx, "transaction_type", "") or "").replace(" ", "_").lower())
            mapped = transaction_type_TX_MAP.get(tx_key)
            src_asset_fallback = mapped[2] if mapped else ""
            dst_asset_fallback = mapped[3] if mapped else ""
        except Exception:
            src_asset_fallback = dst_asset_fallback = ""

        dst_asset = ((getattr(tx, "asset_type_destination", "") or "").lower()) or dst_asset_fallback
        src_asset = ((getattr(tx, "asset_type_source", "") or "").lower()) or src_asset_fallback

        if not (ttype == "transfer" and dest_outside):
            if dst_asset == "liquid":
                val = tx.destination_amount if tx.destination_amount is not None else tx.amount
                delta += Decimal(str(val or 0))
    if tx.entity_source_id == entity_id:
        src_outside = _is_outside_account(getattr(tx, "account_source_id", None))
        if not (ttype == "transfer" and src_outside):
            if src_asset == "liquid":
                delta -= Decimal(str(tx.amount or 0))
    return delta


def _planned_tx_to_model_like(planned: dict, fallback_user_id: int) -> Transaction:
    """Create an unsaved Transaction-like object from a dict for simulation.

    Only the fields needed for balance simulations are populated.
    """
    t = Transaction(
        id=None,
        user_id=planned.get("user_id") or planned.get("user", getattr(planned.get("user"), "id", None)) or fallback_user_id,
        date=planned.get("date"),
        amount=planned.get("amount"),
        destination_amount=planned.get("destination_amount"),
        account_source_id=getattr(planned.get("account_source"), "id", planned.get("account_source_id")),
        account_destination_id=getattr(planned.get("account_destination"), "id", planned.get("account_destination_id")),
        posted_at=planned.get("posted_at"),
    )
    # Best-effort additional fields used by entity-level simulation
    try:
        t.transaction_type = planned.get("transaction_type")
        t.entity_source_id = getattr(planned.get("entity_source"), "id", planned.get("entity_source_id"))
        t.entity_destination_id = getattr(planned.get("entity_destination"), "id", planned.get("entity_destination_id"))
        # Derive asset type fallbacks from central mapping when not explicitly present
        tx_key = ((getattr(t, "transaction_type", "") or "").replace(" ", "_").lower())
        mapped = transaction_type_TX_MAP.get(tx_key) or (None, None, None, None)
        src_fallback = (mapped[2] or "") if len(mapped) > 2 else ""
        dst_fallback = (mapped[3] or "") if len(mapped) > 3 else ""
        t.asset_type_source = planned.get("asset_type_source") or src_fallback
        t.asset_type_destination = planned.get("asset_type_destination") or dst_fallback
    except Exception:
        pass
    return t


def _is_outside_account(account_id: Optional[int]) -> bool:
    """Return True if the account is the special Outside account.

    Conventions in this codebase use account_type == 'Outside' and/or name 'Outside'.
    """
    if not account_id:
        return False
    acc = Account.objects.filter(pk=account_id).only("account_type", "account_name").first()
    if not acc:
        return False
    name = (getattr(acc, "account_name", None) or "").strip().lower()
    atype = (getattr(acc, "account_type", None) or "").strip().lower()
    return atype == "outside" or name == "outside"


def validate_no_future_negative_balances(
    original: Transaction,
    replacement_data: dict,
    *,
    for_update: bool = False,
) -> None:
    """Raise ValidationError if applying the replacement would cause any affected
    account balance to go negative at any point from the effective start date forward.

    We simulate the ledger by:
    - Starting from the balance just before min(original.date, replacement.date)
    - Excluding the original row
    - Including the replacement as an in-memory planned transaction
    - Walking forward over visible transactions for involved accounts
    """
    rep_like = _planned_tx_to_model_like(replacement_data, original.user_id)
    start_date = min(original.date, rep_like.date)
    affected_raw = set(
        filter(
            None,
            [
                original.account_source_id,
                original.account_destination_id,
                rep_like.account_source_id,
                rep_like.account_destination_id,
            ],
        )
    )
    # Skip Outside accounts from overdraft simulation
    affected = {aid for aid in affected_raw if not _is_outside_account(aid)}

    # Prepare an in-memory list of planned transactions (only the single replacement)
    planned = [rep_like]
    excluded_ids = [original.id]

    hits: List[NegativeBalanceHit] = []
    for acc_id in affected:
        running = _balance_before(acc_id, original.user_id, start_date)
        # Merge stream: existing rows then inject planned rows at appropriate order
        stream = _stream_after(
            acc_id, original.user_id, start_date, excluded_ids, for_update=for_update
        )
        # Insert the planned replacement respecting ordering
        # For stable ordering on same date, place planned before rows with larger posted_at/id by using None checks
        def key_fn(tx: Transaction):
            # Order by date, then planned (id is None) before persisted (id>0), then id
            return (tx.date, 0 if getattr(tx, "id", None) is None else 1, tx.id or 0)

        merged = stream + planned
        merged.sort(key=key_fn)

        for tx in merged:
            # Only consider transactions that touch this account
            if tx.account_source_id != acc_id and tx.account_destination_id != acc_id:
                continue
            running += _delta_for_account(tx, acc_id)
            if running < 0:
                ent_id = (
                    getattr(tx, "entity_source_id", None)
                    if tx.account_source_id == acc_id
                    else getattr(tx, "entity_destination_id", None)
                )
                hits.append(
                    NegativeBalanceHit(
                        account_id=acc_id,
                        date=getattr(tx, "date", None),
                        balance=running,
                        entity_id=ent_id,
                    )
                )
                break

    if hits:
        # Optional fallback: if enabled, allow when the involved entity has
        # sufficient liquid funds across accounts at all times after start.
        allow_cover = bool(getattr(settings, "ALLOW_ENTITY_COVER_ON_CORRECTION", False) or getattr(settings, "ALLOW_ENTITY_COVER", False))
        if allow_cover:
            h = hits[0]
            ent_id = getattr(h, "entity_id", None)
            if ent_id:
                ent_running = _entity_balance_before(ent_id, original.user_id, start_date)
                ent_stream = _entity_stream_after(
                    ent_id, original.user_id, start_date, excluded_ids, for_update=for_update
                )
                # Include planned replacement in the entity stream as well
                planned = _planned_tx_to_model_like(replacement_data, original.user_id)
                merged_ent = ent_stream + [planned]
                def key_fn2(t: Transaction):
                    return (t.date, 0 if getattr(t, "id", None) is None else 1, t.id or 0)
                merged_ent.sort(key=key_fn2)
                entity_ok = True
                for t in merged_ent:
                    ent_running += _delta_for_entity(t, ent_id)
                    if ent_running < 0:
                        entity_ok = False
                        break
                if entity_ok:
                    # Treat as allowed: no ValidationError. Mark original so the
                    # view can surface a UI hint to add an internal transfer.
                    try:
                        setattr(original, "_entity_cover_used", True)
                        setattr(original, "_entity_cover_account_id", h.account_id)
                        setattr(original, "_entity_cover_entity_id", ent_id)
                        setattr(original, "_entity_cover_date", getattr(h, "date", None))
                    except Exception:
                        pass
                    return
        # Report the first hit (any); include account id and date in the message
        h = hits[0]
        # Build a user-friendly message with account name and guidance
        try:
            acc = Account.objects.filter(pk=h.account_id).select_related("currency").first()
            acc_label = acc.account_name if acc else f"Account #{h.account_id}"
            cur = getattr(acc, "currency", None)
            cur_code = getattr(cur, "code", "") or ""
        except Exception:
            acc_label = f"Account #{h.account_id}"
            cur_code = ""
        dt = getattr(h, "date", None)
        try:
            date_str = dt.strftime("%b %d, %Y") if hasattr(dt, "strftime") else str(dt)
        except Exception:
            date_str = str(dt)
        bal = getattr(h, "balance", None)
        try:
            bal_str = f"{bal:.2f}" if bal is not None else "0.00"
        except Exception:
            bal_str = str(bal) if bal is not None else "0.00"
        prefix = f"{cur_code} " if cur_code else ""
        msg = (
            f"This correction would make {acc_label} go negative on {date_str} "
            f"(projected balance {prefix}{bal_str}). Reduce the amount, add funds before this date, or move the correction to a later date."
        )
        err = ValidationError({"amount": msg})
        # Attach structured details for UI hints
        try:
            setattr(err, "block_account_id", h.account_id)
            setattr(err, "block_entity_id", getattr(h, "entity_id", None))
            setattr(err, "block_date", dt)
            setattr(err, "block_balance", h.balance)
            # Suggested minimal funds to avoid earliest negative
            needed = Decimal("0")
            try:
                if bal is not None and Decimal(str(bal)) < 0:
                    needed = -Decimal(str(bal))
            except Exception:
                needed = Decimal("0")
            setattr(err, "suggest_cover_amount", needed)
            setattr(err, "currency_code", cur_code)
        except Exception:
            pass
        raise err


def validate_delete_no_future_negative_balances(
    original: Transaction,
    *,
    excluded_ids: Optional[Sequence[int]] = None,
    for_update: bool = False,
) -> None:
    """Raise ValidationError if deleting `original` would cause any affected
    account balance to go negative at any point from the original date forward.

    We simulate the ledger by:
    - Starting from the balance just before original.date
    - Excluding the original row (and its hidden child legs are already excluded by default manager)
    - Walking forward over visible transactions for the involved accounts
    """
    start_date = original.date
    affected_raw = set(
        filter(
            None,
            [original.account_source_id, original.account_destination_id],
        )
    )
    # Skip Outside accounts from overdraft simulation
    affected = {aid for aid in affected_raw if not _is_outside_account(aid)}
    # Exclude the targeted original and any additionally planned deletions
    excluded_ids = list(set(([original.id] if original.id else []) + (list(excluded_ids) if excluded_ids else [])))

    hits: List[NegativeBalanceHit] = []
    for acc_id in affected:
        running = _balance_before(acc_id, original.user_id, start_date)
        stream = _stream_after(
            acc_id, original.user_id, start_date, excluded_ids, for_update=for_update
        )
        for tx in stream:
            if tx.account_source_id != acc_id and tx.account_destination_id != acc_id:
                continue
            running += _delta_for_account(tx, acc_id)
            if running < 0:
                ent_id = (
                    getattr(tx, "entity_source_id", None)
                    if tx.account_source_id == acc_id
                    else getattr(tx, "entity_destination_id", None)
                )
                hits.append(
                    NegativeBalanceHit(
                        account_id=acc_id,
                        date=getattr(tx, "date", None),
                        balance=running,
                        entity_id=ent_id,
                    )
                )
                break

    if hits:
        h = hits[0]
        # Friendlier message for delete overdraft
        allow_cover = bool(getattr(settings, "ALLOW_ENTITY_COVER_ON_DELETE", False) or getattr(settings, "ALLOW_ENTITY_COVER", False))
        if allow_cover:
            ent_id = getattr(h, "entity_id", None)
            if ent_id:
                ent_running = _entity_balance_before(ent_id, original.user_id, start_date)
                ent_stream = _entity_stream_after(
                    ent_id, original.user_id, start_date, excluded_ids, for_update=for_update
                )
                def key_fn2(t: Transaction):
                    return (t.date, 0 if getattr(t, "id", None) is None else 1, t.id or 0)
                ent_ok = True
                for t in ent_stream:
                    ent_running += _delta_for_entity(t, ent_id)
                    if ent_running < 0:
                        ent_ok = False
                        break
                if ent_ok:
                    try:
                        setattr(original, "_entity_cover_used", True)
                        setattr(original, "_entity_cover_account_id", h.account_id)
                        setattr(original, "_entity_cover_entity_id", ent_id)
                        setattr(original, "_entity_cover_date", getattr(h, "date", None))
                    except Exception:
                        pass
                    return
        try:
            acc = Account.objects.filter(pk=h.account_id).select_related("currency").first()
            acc_label = acc.account_name if acc else f"Account #{h.account_id}"
            cur_code = getattr(getattr(acc, "currency", None), "code", "") or ""
        except Exception:
            acc_label = f"Account #{h.account_id}"
            cur_code = ""
        dt = getattr(h, "date", None)
        try:
            date_str = dt.strftime("%b %d, %Y") if hasattr(dt, "strftime") else str(dt)
        except Exception:
            date_str = str(dt)
        bal = getattr(h, "balance", None)
        try:
            bal_str = f"{bal:.2f}" if bal is not None else "0.00"
        except Exception:
            bal_str = str(bal) if bal is not None else "0.00"
        prefix = f"{cur_code} " if cur_code else ""
        msg = (
            f"Deleting this transaction would make {acc_label} go negative on {date_str} "
            f"(projected balance {prefix}{bal_str}). Delete later transactions first, reduce future outflows, or adjust this transaction's date."
        )
        raise ValidationError({"delete": msg})


def reverse_and_hide(txn: Transaction, actor=None) -> None:
    """Create reversal entries for a transaction then hide the original (and child legs).

    Mirrors the behavior used by the UI delete flow so audit and reporting stay consistent.
    """
    if getattr(txn, "is_reversal", False) or getattr(txn, "is_reversed", False):
        return

    related = [txn] + list(Transaction.all_objects.filter(parent_transfer=txn))
    rev_parent = None
    for original in related:
        if getattr(original, "is_reversal", False) or getattr(original, "is_reversed", False):
            continue
        has_both = bool(original.account_source_id and original.account_destination_id)
        if has_both and original.destination_amount is not None:
            amount = original.destination_amount
            dest_amount = original.amount
        else:
            amount = original.amount
            dest_amount = None

        rev = Transaction.objects.create(
            user=original.user,
            date=timezone.now().date(),
            description=f"Reversal of {original.description}",
            transaction_type=original.transaction_type,
            amount=amount,
            destination_amount=dest_amount,
            account_source=original.account_destination,
            account_destination=original.account_source,
            entity_source=original.entity_destination,
            entity_destination=original.entity_source,
            currency=original.currency,
            parent_transfer=rev_parent if original is not txn else None,
            is_hidden=True,
            is_reversal=True,
            reversed_transaction=original,
        )
        if original is txn:
            rev_parent = rev
        original.is_reversed = True
        original.reversed_at = timezone.now()
        if actor is not None:
            original.reversed_by = actor
        original.ledger_status = "reversed"
        original.save(
            update_fields=["is_reversed", "reversed_at", "reversed_by", "ledger_status"]
        )

    Transaction.all_objects.filter(Q(pk=txn.pk) | Q(parent_transfer=txn)).update(is_hidden=True)


def correct_transaction(original: Transaction, new_data: dict, actor=None) -> Transaction:
    """Perform an immutable correction:
    - Validate that replacing `original` with `new_data` won't produce negative future balances
    - If valid, reverse+hide the original, then create and save the replacement

    Returns the saved replacement transaction.
    """
    # Ensure required basics for simulation
    if "date" not in new_data:
        new_data = dict(new_data)
        new_data["date"] = original.date
    if "user" not in new_data and "user_id" not in new_data:
        new_data = dict(new_data)
        new_data["user_id"] = original.user_id

    # Perform validation and mutation atomically and with row locks to avoid races
    with db_tx.atomic():
        validate_no_future_negative_balances(original, new_data, for_update=True)
        # Reverse and hide the original
        reverse_and_hide(original, actor=actor)

        # Create replacement
        # Ensure a currency is present to satisfy model validation. Derive it
        # similarly to TransactionForm.save() and Transaction.save().
        if not new_data.get("currency"):
            try:
                acc_src = new_data.get("account_source")
                acc_dst = new_data.get("account_destination")
                tx_type = (new_data.get("transaction_type") or "").lower()
                cur = None
                if tx_type == "income" and acc_dst and getattr(acc_dst, "currency", None):
                    cur = acc_dst.currency
                elif acc_src and getattr(acc_src, "currency", None):
                    cur = acc_src.currency
                elif acc_dst and getattr(acc_dst, "currency", None):
                    cur = acc_dst.currency
                else:
                    # fall back to user's base currency when available
                    cur = getattr(original.user, "base_currency", None)
                if cur is not None:
                    new_data = dict(new_data)
                    new_data["currency"] = cur
            except Exception:
                pass
        replacement = Transaction(**new_data)
        # Ensure default fields and model validations are applied
        replacement.full_clean()
        replacement.save()
        return replacement
