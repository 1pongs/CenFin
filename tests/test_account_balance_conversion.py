from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Account
from currencies.models import Currency
from entities.models import Entity
from transactions.models import Transaction


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class AccountBalanceConversionTests(TestCase):
    def setUp(self):
        self.cur = Currency.objects.create(code="USD", name="US Dollar")
        User = get_user_model()
        self.user = User.objects.create_user(username="acc", password="p")
        self.account = Account.objects.create(
            account_name="Cash", account_type="Cash", currency=self.cur, user=self.user
        )

    def test_same_currency_returns_current_balance(self):
        balance = self.account.get_current_balance()
        conv = self.account.balance_in_currency("USD")
        self.assertEqual(conv, balance)