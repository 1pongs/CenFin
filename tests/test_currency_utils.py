from decimal import Decimal

from django.test import TestCase, override_settings
from currencies.models import Currency, ExchangeRate
from utils.currency import convert_amount
from unittest.mock import patch


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
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


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class ConvertAmountFetchTests(TestCase):
    def setUp(self):
        self.cur_usd = Currency.objects.create(code="USD", name="US Dollar")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")

    @patch("utils.currency.requests.get")
    def test_fetch_from_frankfurter(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"rates": {"PHP": "55.0"}}
        mock_get.return_value.raise_for_status = lambda: None

        amt = Decimal("10")
        result = convert_amount(amt, self.cur_usd, self.cur_php)
        self.assertEqual(result, Decimal("550"))
        rate = ExchangeRate.objects.get(
            currency_from=self.cur_usd, currency_to=self.cur_php
        )
        self.assertEqual(rate.rate, Decimal("55.0"))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class FrankfurterServiceTests(TestCase):
    @patch("currencies.services.requests.get")
    def test_returns_all_remote_codes(self, mock_get):
        from currencies import services
        from django.core.cache import cache

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"USD": "US Dollar", "EUR": "Euro"}
        mock_get.return_value.raise_for_status = lambda: None

        cache.clear()
        # Only USD exists locally but service should return both USD and EUR
        Currency.objects.create(code="USD", name="US Dollar")
        data = services.get_frankfurter_currencies()
        self.assertEqual(set(data.keys()), {"USD", "EUR"})
