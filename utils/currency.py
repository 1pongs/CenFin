from decimal import Decimal
from typing import Union
from currencies.models import Currency, ExchangeRate, get_rate
import requests

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
    code = request.session.get("active_currency") or request.session.get("currency")
    if not code and request.user.is_authenticated and getattr(request.user, "base_currency_id", None):
        code = request.user.base_currency.code
    if not code:
        return None
    return Currency.objects.filter(code=code).first()


def convert_amount(amount: Decimal, orig_currency: Union[str, Currency], target_currency: Union[str, Currency], *, user=None, source=None) -> Decimal:
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
    if source is None and user is not None and hasattr(user, "preferred_rate_source"):
        source = user.preferred_rate_source
    if source is None:
        source = "FRANKFURTER"
    rate = get_rate(orig_currency, target_currency, source, user)
    if rate is None:
        # attempt live fetch from Frankfurter when missing
        try:
            resp = requests.get(
                f"https://api.frankfurter.app/latest?from={orig_currency.code}&to={target_currency.code}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            rate_val = Decimal(str(data["rates"][target_currency.code]))
            ExchangeRate.objects.update_or_create(
                source="FRANKFURTER",
                currency_from=orig_currency,
                currency_to=target_currency,
                user=user,
                defaults={"rate": rate_val},
            )
            rate = rate_val
        except Exception:
            return amount
    return amount * rate


def amount_for_display(request, amount: Decimal, orig_currency: Union[str, Currency]) -> Decimal:
    target = get_active_currency(request)
    if not target:
        return amount
    return convert_amount(amount, orig_currency, target, user=getattr(request, "user", None))