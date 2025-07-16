from decimal import Decimal
from django.test import TestCase, override_settings
from currencies.models import Currency
from utils.currency import convert_amount
from django.contrib.auth import get_user_model
from unittest.mock import patch


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


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ConvertAmountUserRateTests(TestCase):
    def setUp(self):
        self.cur_usd = Currency.objects.create(code="USD", name="US Dollar")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        User = get_user_model()
        self.user = User.objects.create_user(
            username="u", password="p", preferred_rate_source="USER"
        )

    def test_no_external_fetch_when_user_rate_missing(self):
        amt = Decimal("10")
        with patch("utils.currency.requests.get") as mock_get:
            result = convert_amount(
                amt, self.cur_usd, self.cur_php, user=self.user
            )
            self.assertEqual(result, amt)
            mock_get.assert_not_called()