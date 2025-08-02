from .models import Currency
from . import services
from utils.currency import get_active_currency, get_currency_symbol


def currency_context(request):
    """Provide currency info for templates.

    The dropdown should list every currency supported by Frankfurter. We
    attempt to fetch that list and ensure corresponding ``Currency`` objects
    exist in the database so conversions will work even for newly added
    codes. If the external service is unavailable we fall back to whatever is
    already stored locally.
    """

    try:
        remote = services.get_frankfurter_currencies()
        currencies = []
        for code, name in remote.items():
            obj, _ = Currency.objects.get_or_create(code=code, defaults={"name": name})
            if obj.name != name:
                obj.name = name
                obj.save(update_fields=["name"])
            currencies.append(obj)
        currencies.sort(key=lambda c: c.code)
    except services.CurrencySourceError:
        currencies = list(Currency.objects.filter(is_active=True))

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
