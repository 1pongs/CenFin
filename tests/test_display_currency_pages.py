from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from currencies.models import Currency, ExchangeRate
from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class DisplayCurrencyPageTests(TestCase):
    def setUp(self):
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        ExchangeRate.objects.create(currency_from=self.cur_php, currency_to=self.cur_krw, rate=Decimal("25"))
        ExchangeRate.objects.create(currency_from=self.cur_krw, currency_to=self.cur_php, rate=Decimal("0.04"))
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.acc_php = Account.objects.create(account_name="PHP", account_type="Cash", user=self.user, currency=self.cur_php)
        self.entity = Entity.objects.create(entity_name="Ent", entity_type="personal fund", user=self.user)
        Transaction.objects.create(
            user=self.user,
            transaction_type="income",
            amount=Decimal("100"),
            account_destination=self.acc_php,
            entity_destination=self.entity,
            currency=self.cur_php,
        )

    def test_tx_amount_not_blank(self):
        session = self.client.session
        session["display_currency"] = "KRW"
        session.save()
        resp = self.client.get(reverse("transactions:transaction_list"))
        self.assertContains(resp, "KRW")

    def test_entity_total_converts(self):
        session = self.client.session
        session["display_currency"] = "KRW"
        session.save()
        resp = self.client.get(reverse("entities:list"))
        self.assertContains(resp, "KRW")