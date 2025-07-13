from .models import Currency
from utils.currency import get_active_currency, get_currency_symbol


def currency_context(request):
    currencies = Currency.objects.filter(is_active=True)
    active = get_active_currency(request)
    base = None
    if request.user.is_authenticated:
        base = getattr(request.user, "base_currency", None)
    symbol = get_currency_symbol(active.code) if active else ""
    return {
        "currency_options": currencies,
        "active_currency": active,
        "active_currency_symbol": symbol,
        "base_currency": base,
    }
