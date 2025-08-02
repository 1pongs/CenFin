from decimal import Decimal
from django.test import TestCase, override_settings

from currencies.models import Currency, ExchangeRate
from utils.conversion import convert_amount, MissingRateError


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ConversionWrapperTests(TestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.php = Currency.objects.create(code="PHP", name="Peso")

    def test_missing_rate_raises(self):
        with self.assertRaises(MissingRateError):
            convert_amount(Decimal("1"), "USD", "PHP")

    def test_converts_when_rate_present(self):
        ExchangeRate.objects.create(currency_from=self.usd, currency_to=self.php, rate=Decimal("50"))
        result = convert_amount(Decimal("2"), "USD", "PHP")
        self.assertEqual(result, Decimal("100"))