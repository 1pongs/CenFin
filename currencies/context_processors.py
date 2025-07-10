from .models import Currency


def currency_context(request):
    currencies = Currency.objects.filter(is_active=True)
    code = request.session.get("currency")
    if not code and request.user.is_authenticated and request.user.base_currency:
        code = request.user.base_currency.code
    active = currencies.filter(code=code).first()
    return {"currency_options": currencies, "active_currency": active}
