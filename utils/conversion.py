from decimal import Decimal
from currencies.models import Currency, get_rate
from utils.currency import convert_amount as _convert_amount


class MissingRateError(Exception):
    """Raised when an exchange rate is missing."""


def convert_amount(amount: Decimal, from_code: str, to_code: str) -> Decimal:
    """Convert ``amount`` from ``from_code`` to ``to_code``.

    Unlike ``utils.currency.convert_amount`` this helper raises
    :class:`MissingRateError` if either currency or the exchange rate is
    missing.
    """

    frm = Currency.objects.filter(code=from_code).first()
    to = Currency.objects.filter(code=to_code).first()
    if not frm or not to:
        raise MissingRateError("Unknown currency")
    if get_rate(frm, to) is None:
        raise MissingRateError(f"No rate for {from_code}->{to_code}")
    return _convert_amount(amount, frm, to)
