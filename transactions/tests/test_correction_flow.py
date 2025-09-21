from decimal import Decimal

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from transactions.services import correct_transaction
from django.core.exceptions import ValidationError


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class CorrectionFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)

    def test_block_negative_future_balance(self):
        # Start with 100 in, then 90 out -> leaves 10
        t_in = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        t_out = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="spend",
            transaction_type="expense",
            amount=Decimal("90"),
            account_source=self.acc,
            account_destination=None,
            entity_source=self.ent,
            entity_destination=None,
        )
        # Correct the income down to 80 (reduces future balance to -10)
        with self.assertRaises(ValidationError):
            correct_transaction(
                t_in,
                {
                    "user": self.user,
                    "date": t_in.date,
                    "description": "seed-corr",
                    "transaction_type": "income",
                    "amount": Decimal("80"),
                    "account_source": self.acc,
                    "account_destination": self.acc,
                    "entity_source": self.ent,
                    "entity_destination": self.ent,
                },
                actor=self.user,
            )

    def test_allow_non_negative_correction(self):
        t_in = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        t_out = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="spend",
            transaction_type="expense",
            amount=Decimal("70"),
            account_source=self.acc,
            account_destination=None,
            entity_source=self.ent,
            entity_destination=None,
        )
        # Correct income to 80 (still leaves +10 balance)
        rep = correct_transaction(
            t_in,
            {
                "user": self.user,
                "date": t_in.date,
                "description": "seed-corr",
                "transaction_type": "income",
                "amount": Decimal("80"),
                "account_source": self.acc,
                "account_destination": self.acc,
                "entity_source": self.ent,
                "entity_destination": self.ent,
            },
            actor=self.user,
        )
        self.assertIsInstance(rep, Transaction)
        # Original should be marked reversed/hidden
        t_in.refresh_from_db()
        self.assertTrue(t_in.is_reversed)
        self.assertTrue(t_in.is_hidden)

    def test_correction_infers_currency_when_omitted(self):
        # Seed a simple expense that we will correct
        tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="spend",
            transaction_type="expense",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        # Build replacement data WITHOUT a currency and ensure the service/view logic
        # is able to infer it from the account/user so validation passes.
        rep = correct_transaction(
            tx,
            {
                "user": self.user,
                "date": tx.date,
                "description": "spend-corr",
                "transaction_type": "expense",
                "amount": Decimal("9"),
                "account_source": self.acc,
                "account_destination": self.acc,
                "entity_source": self.ent,
                "entity_destination": self.ent,
                # intentionally no 'currency'
            },
            actor=self.user,
        )
        self.assertIsInstance(rep, Transaction)
        self.assertIsNotNone(rep.currency)
