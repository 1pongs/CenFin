from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from currencies.models import Currency
from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from cenfin_proj.utils import get_account_entity_balance


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class EntityAccountBalanceFilterTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(code="PHP", name="Peso")
        User = get_user_model()
        self.user = User.objects.create_user(username="entity-user", password="pw")
        self.account = Account.objects.create(
            account_name="Cash",
            account_type="Cash",
            user=self.user,
            currency=self.currency,
        )
        self.entity = Entity.objects.create(
            entity_name="Farm",
            entity_type="business fund",
            user=self.user,
        )
        self.client.force_login(self.user)

    def _create_inflow(self, amount, **extra):
        return Transaction.objects.create(
            user=self.user,
            transaction_type="income",
            amount=Decimal(amount),
            account_destination=self.account,
            entity_destination=self.entity,
            currency=self.currency,
            **extra,
        )

    def test_deleted_transactions_do_not_count_toward_entity_balance(self):
        self._create_inflow("100")
        self._create_inflow("9300", is_deleted=True)

        pair_balance = get_account_entity_balance(self.account.id, self.entity.id, user=self.user)
        self.assertEqual(pair_balance, Decimal("100"))
        self.assertEqual(self.account.get_current_balance(), Decimal("100"))

        resp = self.client.get(reverse("entities:accounts", args=[self.entity.pk]))
        self.assertEqual(resp.status_code, 200)
        balances = {row["name"]: row["balance"] for row in resp.context["accounts"]}
        self.assertEqual(balances["Cash"], Decimal("100"))
        self.assertEqual(resp.context["total_balance"], Decimal("100"))

    def test_reversal_transactions_are_ignored(self):
        base = self._create_inflow("200")
        Transaction.objects.create(
            user=self.user,
            transaction_type="income",
            amount=Decimal("-200"),
            account_destination=self.account,
            entity_destination=self.entity,
            currency=self.currency,
            is_reversal=True,
            reversed_transaction=base,
        )

        pair_balance = get_account_entity_balance(self.account.id, self.entity.id, user=self.user)
        self.assertEqual(pair_balance, Decimal("200"))
        self.assertEqual(self.account.get_current_balance(), Decimal("200"))

        resp = self.client.get(reverse("entities:accounts", args=[self.entity.pk]))
        self.assertEqual(resp.status_code, 200)
        balances = {row["name"]: row["balance"] for row in resp.context["accounts"]}
        self.assertEqual(balances["Cash"], Decimal("200"))
        self.assertEqual(resp.context["total_balance"], Decimal("200"))

    def test_unassigned_outflow_does_not_reduce_entity_balance(self):
        self._create_inflow("15000")
        Transaction.objects.create(
            user=self.user,
            transaction_type="expense",
            amount=Decimal("9300"),
            account_source=self.account,
            currency=self.currency,
        )

        pair_balance = get_account_entity_balance(self.account.id, self.entity.id, user=self.user)
        self.assertEqual(pair_balance, Decimal("15000"))
        self.assertEqual(self.account.get_current_balance(), Decimal("5700"))

        resp = self.client.get(reverse("entities:accounts", args=[self.entity.pk]))
        self.assertEqual(resp.status_code, 200)
        balances = {row["name"]: row["balance"] for row in resp.context["accounts"]}
        self.assertEqual(balances["Cash"], Decimal("15000"))
