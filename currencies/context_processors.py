from .models import Currency
from utils.currency import get_active_currency


def currency_context(request):
    currencies = Currency.objects.filter(is_active=True)
    active = get_active_currency(request)
    return {"currency_options": currencies, "active_currency": active}
