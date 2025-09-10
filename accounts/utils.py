from .models import Account


def ensure_outside_account():
    """Return the shared Outside account, creating it if needed."""
    acc, _ = Account.objects.get_or_create(
        account_name="Outside",
        user=None,
        defaults={"account_type": "Outside", "is_visible": False},
    )
    return acc


def get_remittance_account(user, currency):
    """Return or create the remittance account for ``currency``."""
    from currencies.models import Currency
    from entities.utils import ensure_remittance_entity

    if isinstance(currency, str):
        currency = Currency.objects.filter(code=currency).first()
    if currency is None:
        return None

    ensure_remittance_entity(user)
    name = f"Remittance {currency.code}"
    acc, _ = Account.objects.get_or_create(
        account_name=name,
        user=user,
        defaults={
            "account_type": "Banks",
            "currency": currency,
            "is_visible": False,
            "system_hidden": True,
        },
    )
    return acc


def ensure_remittance_account(user):
    """Ensure a single hidden Remittance account exists for the user.

    This replaces the per-currency remittance accounts. The account is hidden
    from lists/forms (is_visible=False, system_hidden=True) and is used only as
    an internal bridge for cross-currency transfers so child legs can have both
    account references populated.
    """
    # Default currency: user's base currency if set, otherwise PHP
    from currencies.models import Currency

    default_currency = None
    if getattr(user, "base_currency_id", None):
        default_currency = user.base_currency
    else:
        default_currency = Currency.objects.filter(code="PHP").first()

    acc, _ = Account.objects.get_or_create(
        account_name="Remittance",
        user=user,
        defaults={
            "account_type": "Banks",
            "currency": default_currency,
            "is_visible": False,
            "system_hidden": True,
        },
    )
    return acc
