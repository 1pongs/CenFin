from decimal import Decimal, ROUND_HALF_UP
from currencies.models import ExchangeRate, Currency
import requests


def ensure_rate(frm: str, to: str) -> Decimal:
    """Return frm→to rate, fetching and caching if missing."""
    if frm == to:
        return Decimal("1")
    try:
        return ExchangeRate.objects.get(
            currency_from__code=frm, currency_to__code=to
        ).rate
    except ExchangeRate.DoesNotExist:
        resp = requests.get(
            f"https://api.frankfurter.app/latest?amount=1&from={frm}&to={to}",
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = Decimal(str(data["rates"][to])).quantize(Decimal("0.0001"))
        ExchangeRate.objects.update_or_create(
            currency_from=Currency.objects.get(code=frm),
            currency_to=Currency.objects.get(code=to),
            defaults={"rate": rate},
        )
        return rate


def convert(amount: Decimal, frm: str, to: str) -> Decimal:
    """Convert ``amount`` from currency ``frm`` to ``to``."""
    return (amount * ensure_rate(frm, to)).quantize(Decimal("0.01"), ROUND_HALF_UP)