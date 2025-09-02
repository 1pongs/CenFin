from decimal import Decimal
from datetime import date
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from liabilities.models import CreditCard, Lender
from accounts.models import Account
from django.core.exceptions import ValidationError
from transactions.forms import TransactionForm
from transactions.models import Transaction
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
        self.client.force_login(self.user)

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

    def test_account_str_omits_limit(self):
        card = CreditCard.objects.create(
            user=self.user,
            issuer=self.lender,
            card_name="Visa",
            credit_limit=Decimal("1000"),
            interest_rate=Decimal("1"),
            statement_day=1,
            payment_due_day=10,
        )
        self.assertEqual(str(card.account), "Visa")

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
        self.assertEqual(card.outstanding_amount, Decimal("200"))
        self.assertEqual(card.available_credit, Decimal("800"))

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

    def test_soft_delete_then_readd(self):
        card = CreditCard.objects.create(
            user=self.user,
            issuer=self.lender,
            card_name="Visa",
            credit_limit=Decimal("1000"),
            interest_rate=Decimal("1"),
            statement_day=1,
            payment_due_day=10,
        )
        acc_id = card.account_id
        card.delete()

        resp = self.client.post(
            reverse("liabilities:credit-create"),
            {
                "issuer_id": self.lender.pk,
                "issuer_text": self.lender.name,
                "card_name": "Visa",
                "credit_limit": "1000",
                "interest_rate": "1",
                "statement_day": "1",
                "payment_due_day": "10",
            },
        )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Account.objects.filter(
                account_name="Visa", user=self.user, is_active=True
            ).count(),
            1,
        )
        acc = Account.objects.get(account_name="Visa", user=self.user)
        self.assertEqual(acc.pk, acc_id)

    def test_active_conflict(self):
        Account.objects.create(
            account_name="Master", account_type="Cash", user=self.user
        )
        resp = self.client.post(
            reverse("liabilities:credit-create"),
            {
                "issuer_id": self.lender.pk,
                "issuer_text": self.lender.name,
                "card_name": "Master",
                "credit_limit": "1000",
                "interest_rate": "1",
                "statement_day": "1",
                "payment_due_day": "10",
            },
        )
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertIn("card_name", form.errors)

    def test_payment_limits_and_updates_balance(self):
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
        # simulate existing spend to create balance
        Transaction.objects.create(
            user=self.user,
            date=date(2025, 1, 1),
            transaction_type="expense",
            amount=Decimal("300"),
            account_source=card.account,
            account_destination=cash,
            entity_source=self.acc_ent,
            entity_destination=self.entity,
        )
        card.refresh_from_db()
        self.assertEqual(card.outstanding_amount, Decimal("300"))
        self.assertEqual(card.available_credit, Decimal("700"))

        form = TransactionForm(
            data={
                "date": "2025-02-01",
                "description": "Pay",
                "transaction_type": "cc_payment",
                "amount": "400",
                "account_source": cash.pk,
                "account_destination": card.account.pk,
                "entity_source": self.acc_ent.pk,
                "entity_destination": self.out_ent.pk,
            },
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

        form = TransactionForm(
            data={
                "date": "2025-02-01",
                "description": "Pay",
                "transaction_type": "cc_payment",
                "amount": "200",
                "account_source": cash.pk,
                "account_destination": card.account.pk,
                "entity_source": self.acc_ent.pk,
                "entity_destination": self.out_ent.pk,
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        card.refresh_from_db()
        self.assertEqual(card.outstanding_amount, Decimal("100"))
        self.assertEqual(card.available_credit, Decimal("900"))

    def test_transaction_delete_updates_balance(self):
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
        tx = Transaction.objects.create(
            user=self.user,
            date=date(2025, 1, 1),
            transaction_type="expense",
            amount=Decimal("200"),
            account_source=card.account,
            account_destination=cash,
            entity_source=self.acc_ent,
            entity_destination=self.entity,
        )
        card.refresh_from_db()
        self.assertEqual(card.outstanding_amount, Decimal("200"))
        tx.delete()
        card.refresh_from_db()
        self.assertEqual(card.outstanding_amount, Decimal("0"))
        self.assertEqual(card.available_credit, Decimal("1000"))