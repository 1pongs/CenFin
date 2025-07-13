from decimal import Decimal
from django.test import TestCase, override_settings
from currencies.models import Currency
from utils.currency import convert_amount


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ConvertAmountMissingCurrencyTests(TestCase):
    def test_missing_currency_returns_amount(self):
        Currency.objects.create(code="USD", name="US Dollar")
        amount = Decimal("100")
        # orig currency not in DB
        result = convert_amount(amount, "PHP", "USD")
        self.assertEqual(result, amount)
        # target currency missing
        result = convert_amount(amount, "USD", "PHP")
        self.assertEqual(result, amount)