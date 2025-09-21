from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from currencies.models import Currency, ExchangeRate
from accounts.models import Account
from transactions.models import Transaction


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class CurrencyDisplayTests(TestCase):
    def setUp(self):
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        ExchangeRate.objects.create(
            currency_from=self.cur_php, currency_to=self.cur_krw, rate=Decimal("1250")
        )
        ExchangeRate.objects.create(
            currency_from=self.cur_krw, currency_to=self.cur_php, rate=Decimal("0.0008")
        )
        User = get_user_model()
        self.user = User.objects.create_user(username="u2", password="p")
        self.client.force_login(self.user)
        self.acc_php = Account.objects.create(
            account_name="PHP",
            account_type="Cash",
            user=self.user,
            currency=self.cur_php,
        )
        self.acc_krw = Account.objects.create(
            account_name="KRW",
            account_type="Cash",
            user=self.user,
            currency=self.cur_krw,
        )
        Transaction.objects.create(
            user=self.user,
            transaction_type="transfer",
            amount=Decimal("100"),
            account_source=self.acc_php,
            account_destination=self.acc_krw,
            currency=self.cur_php,
        )

    def test_php_to_krw_conversion(self):
        session = self.client.session
        session["display_currency"] = "KRW"
        session.save()
        resp = self.client.get(reverse("transactions:transaction_list"))
        self.assertContains(resp, "125,000.00 KRW")
