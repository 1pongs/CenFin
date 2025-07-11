from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from liabilities.models import CreditCard, Lender
from accounts.models import Account
from transactions.forms import TransactionForm
from entities.models import Entity
from entities.utils import ensure_fixed_entities
from accounts.utils import ensure_outside_account

@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class CreditCardAccountTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cc", password="p")
        self.lender = Lender.objects.create(name="CardBank")
        self.entity = Entity.objects.create(entity_name="Vendor", entity_type="personal fund", user=self.user)
        self.outside_acc = ensure_outside_account()
        self.out_ent, self.acc_ent = ensure_fixed_entities(self.user)

    def test_account_auto_created(self):
        card = CreditCard.objects.create(
            user=self.user,
            issuer=self.lender,
            card_name="Visa",
            credit_limit=Decimal("1000"),
            interest_rate=Decimal("1"),
            statement_day=1,
            payment_due_day=10,
        )
        self.assertIsNotNone(card.account)
        self.assertEqual(card.account.account_type, "Credit")

    def test_card_shown_in_form(self):
        card = CreditCard.objects.create(
            user=self.user,
            issuer=self.lender,
            card_name="Visa",
            credit_limit=Decimal("500"),
            interest_rate=Decimal("1"),
            statement_day=1,
            payment_due_day=10,
        )
        form = TransactionForm(user=self.user)
        self.assertIn(card.account, form.fields["account_source"].queryset)

    def test_spend_updates_balance_and_enforces_limit(self):
        card = CreditCard.objects.create(
            user=self.user,
            issuer=self.lender,
            card_name="Visa",
            credit_limit=Decimal("1000"),
            interest_rate=Decimal("1"),
            statement_day=1,
            payment_due_day=10,
        )
        cash = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        form = TransactionForm(
            data={
                "date": "2025-01-01",
                "description": "Buy",
                "transaction_type": "expense",
                "amount": "200",
                "account_source": card.account.pk,
                "account_destination": cash.pk,
                "entity_source": self.acc_ent.pk,
                "entity_destination": self.entity.pk,
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        card.refresh_from_db()
        self.assertEqual(card.current_balance, Decimal("200"))

        form = TransactionForm(
            data={
                "date": "2025-01-02",
                "description": "Big Buy",
                "transaction_type": "expense",
                "amount": "900",
                "account_source": card.account.pk,
                "account_destination": cash.pk,
                "entity_source": self.acc_ent.pk,
                "entity_destination": self.entity.pk,
            },
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("account_source", form.errors)