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
    """Return net totals per entity converted to ``disp_code``."""

    totals: dict[int, Decimal] = defaultdict(Decimal)
    txs = (
        Transaction.objects.filter(user=user)
        .select_related("currency", "account_destination__currency")
    )
    for tx in txs:
        if tx.amount is None or tx.currency is None:
            continue
        # Always treat the source leg in the transaction's own currency.
        if tx.entity_source_id:
            totals[tx.entity_source_id] -= convert_amount(
                tx.amount, tx.currency.code, disp_code
            )

        if tx.entity_destination_id:
            # For the destination side, prefer the explicitly stored
            # destination_amount and the destination account's currency.  This
            # ensures cross-currency transfers respect the destination account's
            # base currency.
            dest_amt = tx.destination_amount if tx.destination_amount is not None else tx.amount
            dest_code = (
                tx.account_destination.currency.code
                if tx.destination_amount is not None
                and tx.account_destination_id
                and tx.account_destination
                and tx.account_destination.currency
                else tx.currency.code
            )
            totals[tx.entity_destination_id] += convert_amount(
                dest_amt, dest_code, disp_code
            )

    return totals
