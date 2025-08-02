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
from core.utils.currency import convert


def get_entity_aggregate_rows(user, display_code: str):
    """Return liquid totals per entity converted to ``display_code``."""

    rows = defaultdict(lambda: {"liquid": Decimal("0"), "nonliquid": Decimal("0")})
    txs = Transaction.objects.filter(user=user).select_related("currency")
    for tx in txs:
        amount = tx.amount or Decimal("0")
        cur_code = tx.currency.code if tx.currency else display_code
        conv = convert(amount, cur_code, display_code)
        if tx.entity_destination_id:
            if (tx.asset_type_destination or "").lower() == "liquid":
                rows[tx.entity_destination_id]["liquid"] += conv
            elif (tx.asset_type_destination or "").replace("-", "_").lower() == "non_liquid":
                rows[tx.entity_destination_id]["nonliquid"] += conv
        if tx.entity_source_id:
            if (tx.asset_type_source or "").lower() == "liquid":
                rows[tx.entity_source_id]["liquid"] -= conv
            elif (tx.asset_type_source or "").replace("-", "_").lower() == "non_liquid":
                rows[tx.entity_source_id]["nonliquid"] -= conv
    return rows
