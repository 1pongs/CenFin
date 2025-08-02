"""Utility helpers for currency conversion and display."""

from decimal import Decimal
from typing import Union

import requests

from currencies.models import Currency, ExchangeRate, get_rate


# Map a few common currency codes to their display symbols. Used when
# rendering monetary values in templates and JSON responses.
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "KRW": "₩",
    "PHP": "₱",
}


def get_currency_symbol(code: str) -> str:
    """Return the typical symbol for ``code`` or the code itself."""

    return CURRENCY_SYMBOLS.get(code.upper(), code)
    

def get_active_currency(request) -> Currency | None:
    """Return the active currency for the current request."""

    code = request.session.get("active_currency") or request.session.get("currency")
    if not code and request.user.is_authenticated and getattr(
        request.user, "base_currency_id", None
    ):
        code = request.user.base_currency.code
    if not code:
        return None
    return Currency.objects.filter(code=code).first()


def convert_amount(
    amount: Decimal,
    orig_currency: Union[str, Currency],
    target_currency: Union[str, Currency],
) -> Decimal:
    """Convert ``amount`` from ``orig_currency`` to ``target_currency``.

    If a conversion rate is missing, an attempt will be made to fetch it from
    the Frankfurter API and store it in the ``ExchangeRate`` table.
    """

    if amount is None:
        return amount

    if isinstance(orig_currency, str):
        orig_currency = Currency.objects.filter(code=orig_currency).first()
        if orig_currency is None:
            return amount
    if isinstance(target_currency, str):
        target_currency = Currency.objects.filter(code=target_currency).first()
        if target_currency is None:
            return amount
    if orig_currency == target_currency:
        return amount

    rate = get_rate(orig_currency, target_currency)
    if rate is None:
        try:
            resp = requests.get(
                f"https://api.frankfurter.app/latest?from={orig_currency.code}&to={target_currency.code}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            rate_val = Decimal(str(data["rates"][target_currency.code]))
            ExchangeRate.objects.update_or_create(
                currency_from=orig_currency,
                currency_to=target_currency,
                defaults={"rate": rate_val},
            )
            rate = rate_val
        except Exception:
            return amount

    return amount * rate


def convert_to_base(
    amount: Decimal,
    orig_currency: Union[str, Currency],
    base_currency: Union[str, Currency] | None = None,
    *,
    request=None,
    user=None,
) -> Decimal:
    """Convert ``amount`` to the application's active/base currency.

    ``base_currency`` can be supplied directly.  If omitted, the active
    currency from ``request`` or the user's ``base_currency`` will be used.
    When no target currency can be determined the original ``amount`` is
    returned.
    """

    if base_currency is None:
        if request is not None:
            base_currency = get_active_currency(request)
            if user is None and hasattr(request, "user"):
                user = request.user
        elif user is not None and getattr(user, "base_currency_id", None):
            base_currency = user.base_currency

    if base_currency is None:
        return amount

    return convert_amount(amount, orig_currency, base_currency)


def amount_for_display(
    request, amount: Decimal, orig_currency: Union[str, Currency]
) -> Decimal:
    """Convert ``amount`` for display based on the request's active currency."""

    target = get_active_currency(request)
    if not target:
        return amount
    return convert_amount(amount, orig_currency, target)
    