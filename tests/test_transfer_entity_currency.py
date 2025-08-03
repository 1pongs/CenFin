from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from currencies.models import Currency, ExchangeRate
from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from entities.utils import get_entity_aggregate_rows


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class EntityAggregateConversionTests(TestCase):
    def setUp(self):
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        ExchangeRate.objects.create(currency_from=self.cur_krw, currency_to=self.cur_php, rate=Decimal("0.04"))
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.entity = Entity.objects.create(entity_name="Fund", entity_type="free fund", user=self.user)
        self.acc_krw = Account.objects.create(account_name="KRW", account_type="Cash", user=self.user, currency=self.cur_krw)
        self.acc_php = Account.objects.create(account_name="PHP", account_type="Cash", user=self.user, currency=self.cur_php)
        Transaction.objects.create(
            user=self.user,
            transaction_type="transfer",
            amount=Decimal("100"),
            account_source=self.acc_krw,
            account_destination=self.acc_php,
            entity_destination=self.entity,
            currency=self.cur_krw,
            destination_amount=Decimal("5"),
        )

    def test_entity_totals_use_destination_currency(self):
        totals = get_entity_aggregate_rows(self.user, "PHP")
        self.assertEqual(totals[self.entity.pk], Decimal("5"))


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class TransferCurrencyAssignmentTests(TestCase):
    def setUp(self):
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        ExchangeRate.objects.create(currency_from=self.cur_krw, currency_to=self.cur_php, rate=Decimal("0.04"))
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.acc_krw = Account.objects.create(account_name="KRW", account_type="Cash", user=self.user, currency=self.cur_krw)
        self.acc_php = Account.objects.create(account_name="PHP", account_type="Cash", user=self.user, currency=self.cur_php)
        self.ent_src = Entity.objects.create(entity_name="Src", entity_type="outside", user=self.user)
        self.ent_dest = Entity.objects.create(entity_name="Dest", entity_type="free fund", user=self.user)

    def test_cross_currency_creates_two_child_transactions(self):
        data = {
            "date": "2024-01-01",
            "description": "x",
            "transaction_type": "transfer",
            "amount": "100",
            "account_source": self.acc_krw.pk,
            "account_destination": self.acc_php.pk,
            "entity_source": self.ent_src.pk,
            "entity_destination": self.ent_dest.pk,
        }
        resp = self.client.post(reverse("transactions:transaction_create"), data)
        self.assertEqual(resp.status_code, 302)
        visible = Transaction.objects.get()
        hidden = Transaction.all_objects.filter(parent_transfer=visible)
        self.assertEqual(hidden.count(), 2)
        outflow = hidden.filter(account_source=self.acc_krw).first()
        inflow = hidden.filter(account_destination=self.acc_php).first()
        self.assertIsNotNone(outflow)
        self.assertIsNotNone(inflow)
        self.assertEqual(outflow.currency, self.cur_krw)
        self.assertEqual(inflow.currency, self.cur_php)
        self.assertEqual(outflow.amount, Decimal("100"))
        self.assertEqual(inflow.amount, Decimal("4"))