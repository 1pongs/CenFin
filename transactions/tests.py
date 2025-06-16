from decimal import Decimal
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import Account
from entities.models import Entity
from .models import Transaction
from .forms import TransactionForm


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionFormAssetTypeTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="test",
            transaction_type="buy product",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_editing_asset_transaction_shows_read_only_choice(self):
        form = TransactionForm(instance=self.tx, user=self.user)
        field = form.fields["transaction_type"]
        self.assertTrue(field.disabled)
        self.assertEqual(field.choices, [("buy product", "Buy Product")])

    def test_new_form_excludes_asset_types(self):
        form = TransactionForm(user=self.user)
        choices = [c[0] for c in form.fields["transaction_type"].choices]
        self.assertNotIn("buy product", choices)
        self.assertNotIn("sell product", choices)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionFormBalanceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="t", password="p")
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Vendor", entity_type="others", user=self.user)
        self.out_acc = Account.objects.create(account_name="Outside", account_type="Outside", user=self.user)
        self.out_ent = Entity.objects.create(entity_name="Outside", entity_type="outside", user=self.user)

    def _form_data(self, **overrides):
        data = {
            "date": timezone.now().date(),
            "description": "Test",
            "transaction_type": "income",
            "amount": "50",
            "account_source": self.acc.pk,
            "account_destination": self.acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        data.update(overrides)
        return data

    def test_insufficient_balance_shows_errors(self):
        form = TransactionForm(data=self._form_data(amount="50"), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("account_source", form.errors)
        self.assertIn("entity_source", form.errors)

    def test_outside_skips_balance_check(self):
        # deposit funds to the other side so validation can pass
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.out_acc,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )
        form = TransactionForm(data=self._form_data(account_source=self.out_acc.pk, amount="50"), user=self.user)
        self.assertTrue(form.is_valid())

        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed2",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.acc,
            entity_source=self.out_ent,
            entity_destination=self.out_ent,
        )
        form = TransactionForm(data=self._form_data(entity_source=self.out_ent.pk, amount="50"), user=self.user)
        self.assertTrue(form.is_valid())
