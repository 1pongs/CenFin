from .models import Entity


def ensure_fixed_entities(user=None):
    """Return the Outside and Account entities for ``user``.

    When ``user`` is ``None`` the function will **not** create any new rows and
    simply return existing records if they exist. This behaviour keeps older
    migrations that called this utility without a user from creating orphaned
    entities with ``user_id`` set to ``NULL``.
    """

    if user is None:
        outside = Entity.objects.filter(entity_name="Outside", user__isnull=True).first()
        account = Entity.objects.filter(entity_name="Account", user__isnull=True).first()
        return outside, account
    
    outside, _ = Entity.objects.get_or_create(
        entity_name="Outside",
        user=user,
        defaults={"entity_type": "outside", "is_visible": False},
    )
    defaults = {"entity_type": "free fund", "is_visible": True}
    if hasattr(Entity, "is_account_entity"):
        defaults["is_account_entity"] = True
    if hasattr(Entity, "is_system_default"):
        defaults["is_system_default"] = True
    account, created = Entity.objects.get_or_create(
        entity_name="Account",
        user=user,
        defaults=defaults,
    )
    if not created:
        update_fields = []
        if not account.is_visible:
            account.is_visible = True
            update_fields.append("is_visible")
        if hasattr(account, "is_account_entity") and not account.is_account_entity:
            account.is_account_entity = True
            update_fields.append("is_account_entity")
        if hasattr(account, "is_system_default") and not account.is_system_default:
            account.is_system_default = True
            update_fields.append("is_system_default")
        if update_fields:
            account.save(update_fields=update_fields)
    return outside, account

def ensure_remittance_entity(user):
    """Ensure a hidden Remittance entity exists for the user."""
    ent, _ = Entity.objects.get_or_create(
        entity_name="Remittance",
        user=user,
        defaults={"entity_type": "personal fund", "is_visible": False, "system_hidden": True},
    )
    return ent


from decimal import Decimal
from collections import defaultdict

from transactions.models import Transaction
from utils.currency import convert_amount


def get_entity_aggregate_rows(user, disp_code: str):
    """Return net LIQUID totals per entity converted to ``disp_code``.

    Rules (top-level only):
    - Ignore transfers to/from Outside for liquid balances.
    - Subtract when asset_type_source == 'liquid'.
    - Add when asset_type_destination == 'liquid'.
    Always excludes hidden child legs (parent_transfer__isnull=True).
    """

    totals: dict[int, Decimal] = defaultdict(Decimal)
    txs = (
        Transaction.objects.filter(user=user, parent_transfer__isnull=True)
        .select_related("currency", "account_destination__currency")
    )
    for tx in txs:
        # Skip only pure internal moves where asset class doesn't change
        same_entity = (
            getattr(tx, "entity_source_id", None)
            and getattr(tx, "entity_destination_id", None)
            and tx.entity_source_id == tx.entity_destination_id
        )
        same_account = (
            getattr(tx, "account_source_id", None)
            and getattr(tx, "account_destination_id", None)
            and tx.account_source_id == tx.account_destination_id
        )
        if same_entity or same_account:
            src_t = (getattr(tx, "asset_type_source", "") or "").lower()
            dst_t = (getattr(tx, "asset_type_destination", "") or "").lower()
            if src_t == dst_t:
                continue
        ttype = (getattr(tx, "transaction_type", "") or "").lower()
        dest_outside = bool(
            getattr(tx, "account_destination", None)
            and (
                getattr(tx.account_destination, "account_type", None) == "Outside"
                or getattr(tx.account_destination, "account_name", None) == "Outside"
            )
        )
        src_outside = bool(
            getattr(tx, "account_source", None)
            and (
                getattr(tx.account_source, "account_type", None) == "Outside"
                or getattr(tx.account_source, "account_name", None) == "Outside"
            )
        )

        # Liquid inflow to entity (skip transfers to Outside)
        if (
            tx.entity_destination_id
            and not (ttype == "transfer" and dest_outside)
            and (getattr(tx, "asset_type_destination", "") or "").lower() == "liquid"
        ):
            dest_amt = tx.destination_amount if tx.destination_amount is not None else tx.amount
            if dest_amt is not None:
                dest_code = (
                    tx.account_destination.currency.code
                    if tx.destination_amount is not None
                    and tx.account_destination_id
                    and tx.account_destination
                    and tx.account_destination.currency
                    else (tx.currency.code if tx.currency else None)
                )
                if dest_code:
                    totals[tx.entity_destination_id] += convert_amount(dest_amt, dest_code, disp_code)

        # Liquid outflow from entity (skip transfers from Outside)
        if (
            tx.entity_source_id
            and not (ttype == "transfer" and src_outside)
            and (getattr(tx, "asset_type_source", "") or "").lower() == "liquid"
            and tx.amount is not None
            and tx.currency is not None
        ):
            totals[tx.entity_source_id] -= convert_amount(tx.amount, tx.currency.code, disp_code)

    return totals


def get_entity_non_liquid_totals(user, disp_code: str):
    """Return net non-liquid totals per entity converted to ``disp_code``.

    Rules (top-level only):
    - Treat transfers to Outside as non-liquid inflows (capital in).
    - Treat transfers from Outside as non-liquid outflows (capital out).
    - Otherwise: add when asset_type_destination == 'non_liquid'; subtract when
      asset_type_source == 'non_liquid'.
    Excludes hidden child legs (parent_transfer__isnull=True).
    """
    from collections import defaultdict

    totals: dict[int, Decimal] = defaultdict(Decimal)
    txs = (
        Transaction.objects.filter(user=user, parent_transfer__isnull=True)
        .select_related("currency", "account_destination__currency")
    )
    for tx in txs:
        # Skip only pure internal moves where asset class doesn't change
        same_entity = (
            getattr(tx, "entity_source_id", None)
            and getattr(tx, "entity_destination_id", None)
            and tx.entity_source_id == tx.entity_destination_id
        )
        same_account = (
            getattr(tx, "account_source_id", None)
            and getattr(tx, "account_destination_id", None)
            and tx.account_source_id == tx.account_destination_id
        )
        if same_entity or same_account:
            src_t = (getattr(tx, "asset_type_source", "") or "").lower()
            dst_t = (getattr(tx, "asset_type_destination", "") or "").lower()
            if src_t == dst_t:
                continue
        ttype = (getattr(tx, "transaction_type", "") or "").lower()
        dest_outside = bool(
            getattr(tx, "account_destination", None)
            and (
                getattr(tx.account_destination, "account_type", None) == "Outside"
                or getattr(tx.account_destination, "account_name", None) == "Outside"
            )
        )
        src_outside = bool(
            getattr(tx, "account_source", None)
            and (
                getattr(tx.account_source, "account_type", None) == "Outside"
                or getattr(tx.account_source, "account_name", None) == "Outside"
            )
        )

        # Compute destination-side amount/currency once
        dest_amt = tx.destination_amount if tx.destination_amount is not None else tx.amount
        dest_code = (
            tx.account_destination.currency.code
            if tx.destination_amount is not None
            and tx.account_destination_id
            and tx.account_destination
            and tx.account_destination.currency
            else (tx.currency.code if tx.currency else None)
        )

        # Inflow to non-liquid holdings or capital in (transfer to Outside)
        if tx.entity_destination_id and dest_amt is not None and dest_code is not None:
            if ttype == "transfer" and dest_outside:
                totals[tx.entity_destination_id] += convert_amount(dest_amt, dest_code, disp_code)
            elif (getattr(tx, "asset_type_destination", "") or "").lower() == "non_liquid":
                totals[tx.entity_destination_id] += convert_amount(dest_amt, dest_code, disp_code)

        # Outflow from non-liquid holdings or capital out (transfer from Outside)
        if tx.entity_source_id and tx.amount is not None and tx.currency is not None:
            if ttype == "transfer" and src_outside:
                totals[tx.entity_source_id] -= convert_amount(tx.amount, tx.currency.code, disp_code)
            elif (getattr(tx, "asset_type_source", "") or "").lower() == "non_liquid":
                totals[tx.entity_source_id] -= convert_amount(tx.amount, tx.currency.code, disp_code)

    return totals
