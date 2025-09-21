def label_for_tx(key: str) -> str:
    """Return a human-friendly label for a transaction type key.

    - Accepts either underscore or space separated keys
    - Ensures common abbreviations are capitalized (e.g. 'CC')
    - Title-cases remaining words
    """
    if not key:
        return ""
    norm = key.replace(" ", "_").lower()
    parts = norm.split("_")
    out = []
    for p in parts:
        if p == "cc":
            out.append("CC")
        else:
            out.append(p.capitalize())
    return " ".join(out)

transaction_type_TX_MAP = {
    # tx                tsrc        tdest       assetsrc   assetdest
    "income": ("outside", "income", "outside", "liquid"),
    "expense": ("expense", "outside", "liquid", "outside"),
    "transfer": ("transfer", "transfer", "liquid", "liquid"),
    "buy_acquisition": ("transfer", "buy_acquisition", "liquid", "non_liquid"),
    "sell_acquisition": ("buy_acquisition", "transfer", "non_liquid", "liquid"),
    "loan_disbursement": ("outside", "loan_disbursement", "outside", "liquid"),
    "loan_repayment": ("expense", "outside", "liquid", "outside"),
    "cc_purchase": ("expense", "outside", "credit", "outside"),
    "cc_payment": ("transfer", "transfer", "liquid", "credit"),
}

"""
TXN_TYPE_CHOICES: expose choices for templates and filters using the
space-separated form (e.g. 'buy acquisition') so that the HTML selects
use the same values stored in the database. Internally the
transaction_type_TX_MAP uses underscore keys; model code normalizes by
calling `replace(' ', '_')` when looking up mappings, so keeping the
user-facing values space-separated avoids mismatches between the
filter dropdown and stored rows.
"""
TXN_TYPE_CHOICES = tuple(
    (key.replace("_", " "), label_for_tx(key)) for key in transaction_type_TX_MAP
)

ASSET_TYPE_CHOICES = [
    ("", "---------"),
    ("liquid", "Liquid"),
    ("non_liquid", "Non-Liquid"),
    ("credit", "Credit"),
]

# Map transaction type -> which entity select should be considered the
# "primary" for things like category scoping and template autopop. Values
# are 'source' or 'destination'. Default behavior in forms will fall back to
# 'destination' when unspecified.
ENTITY_SIDE_BY_TX = {
    "income": "destination",
    "transfer": "destination",
    "expense": "source",
    "buy_acquisition": "source",
    "sell_acquisition": "destination",
    "loan_repayment": "source",
    "loan_disbursement": "destination",
    "cc_purchase": "source",
    "cc_payment": "destination",
}

# Mapping to determine which CategoryTag.transaction_type should be used
# when populating the Category dropdown for a given transaction type, and
# which entity side is considered primary for scoping. Keys use underscore
# normalized form (e.g. 'sell_acquisition'). Values may contain:
# - 'category_tx': which transaction_type to filter CategoryTag by
# - 'side': 'source' or 'destination' to override ENTITY_SIDE_BY_TX
# - 'fixed_name': if present, prefer tags whose name matches this fixed label
# Example: for a sell_acquisition we want category tags from 'transfer' and
# scope them to the destination entity.
CATEGORY_SCOPE_BY_TX = {
    "income": {"category_tx": "income", "side": "destination"},
    "transfer": {"category_tx": "transfer", "side": "destination"},
    "expense": {"category_tx": "expense", "side": "source"},
    "buy_acquisition": {"category_tx": "transfer", "side": "source"},
    "sell_acquisition": {"category_tx": "transfer", "side": "destination"},
    "loan_repayment": {"fixed_name": "Loan Repayment", "side": "source"},
    "loan_disbursement": {"fixed_name": "Loan Disbursement", "side": "destination"},
    "cc_purchase": {"category_tx": "expense", "side": "source"},
    "cc_payment": {"fixed_name": "Credit Payment", "side": "destination"},
}
