from django.conf import settings
from utils.conversion import convert_amount, MissingRateError


class CurrencyConversionMixin:
    """Mixin providing queryset balance conversion helpers."""

    def get_display_currency(self):
        return getattr(self.request, "display_currency", settings.BASE_CURRENCY)

    def convert_queryset_balance(
        self, qs, amount_attr="current_balance", currency_attr="currency"
    ):
        """Attach ``converted_balance`` to objects in ``qs``.

        Each object's ``amount_attr`` is converted from its ``currency_attr``'s
        code to the request's display currency.
        """
        disp = self.get_display_currency()
        for obj in qs:
            amount = getattr(obj, amount_attr, None)
            currency = getattr(obj, currency_attr, None)
            code = getattr(currency, "code", None)
            if amount is None or not code:
                obj.converted_balance = None
                continue
            try:
                obj.converted_balance = convert_amount(amount, code, disp)
            except MissingRateError:
                obj.converted_balance = None
        return qs
