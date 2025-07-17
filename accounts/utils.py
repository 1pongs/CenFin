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