from django.conf import settings
from utils.currency import get_currency_symbol


def display_currency(request):
    """Provide display currency code and symbol for templates."""
    code = getattr(request, "display_currency", settings.BASE_CURRENCY)
    symbol = get_currency_symbol(code)
    return {
        "display_currency": code,
        "display_currency_symbol": symbol,
        "active_currency_symbol": symbol,
    }
