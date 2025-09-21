from decimal import Decimal
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import Account
from entities.models import Entity
from currencies.models import Currency
from .models import Transaction
from .ledger import check_lifo_allowed, delete_unit, reverse_unit


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class LedgerSequencingTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )

    def _create_income(self, amt):
        return Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="t",
            transaction_type="income",
            amount=Decimal(str(amt)),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_lifo_delete(self):
        t1 = self._create_income(10)
        t2 = self._create_income(20)
        t3 = self._create_income(30)
        # seq_account should be monotonic
        self.assertEqual([t1.seq_account, t2.seq_account, t3.seq_account], [1, 2, 3])
        # deleting middle should fail
        with self.assertRaises(ValueError):
            delete_unit(t2, "delete_unit_only", self.user)
        # deleting last should work
        delete_unit(t3, "delete_unit_only", self.user)
        t3.refresh_from_db()
        self.assertTrue(t3.is_deleted)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class LedgerPairTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="p", password="p")
        self.acc_a = Account.objects.create(
            account_name="A", account_type="Cash", user=self.user
        )
        self.acc_b = Account.objects.create(
            account_name="B", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")

    def test_pair_block(self):
        gid = uuid.uuid4()
        t1 = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="krw side",
            transaction_type="transfer",
            amount=Decimal("-5000000"),
            account_source=self.acc_a,
            account_destination=self.acc_a,
            entity_source=self.ent,
            entity_destination=self.ent,
            currency=self.cur_krw,
            group_id=gid,
        )
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="php side",
            transaction_type="transfer",
            amount=Decimal("200000"),
            account_source=self.acc_b,
            account_destination=self.acc_b,
            entity_source=self.ent,
            entity_destination=self.ent,
            currency=self.cur_php,
            group_id=gid,
        )
        # create newer txn on account B
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="newer",
            transaction_type="income",
            amount=Decimal("1"),
            account_source=self.acc_b,
            account_destination=self.acc_b,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        ok, blockers = check_lifo_allowed(t1)
        self.assertFalse(ok)
        self.assertTrue(blockers)

    def test_reverse_pair_amounts(self):
        gid = uuid.uuid4()
        t1 = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="krw side",
            transaction_type="transfer",
            amount=Decimal("-5000000"),
            account_source=self.acc_a,
            account_destination=self.acc_a,
            entity_source=self.ent,
            entity_destination=self.ent,
            currency=self.cur_krw,
            group_id=gid,
        )
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="php side",
            transaction_type="transfer",
            amount=Decimal("200000"),
            account_source=self.acc_b,
            account_destination=self.acc_b,
            entity_source=self.ent,
            entity_destination=self.ent,
            currency=self.cur_php,
            group_id=gid,
        )
        revs = reverse_unit(t1, self.user)
        self.assertEqual(len(revs), 2)
        amounts = sorted([r.amount for r in revs])
        self.assertEqual(amounts, [Decimal("-200000"), Decimal("5000000")])


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class IncomeDeleteTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="x", password="p")
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )

    def test_income_delete_only(self):
        t = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="inc",
            transaction_type="income",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        with self.assertRaises(ValueError):
            reverse_unit(t, self.user)
        delete_unit(t, "delete_unit_only", self.user)
        t.refresh_from_db()
        self.assertTrue(t.is_deleted)
