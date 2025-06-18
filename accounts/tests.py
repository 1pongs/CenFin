from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AccountSoftDeleteTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="test",
            transaction_type="transfer",
            amount=Decimal("5"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_edit_delete_restore_account(self):
        # edit
        resp = self.client.post(
            reverse("accounts:edit", args=[self.acc.pk]),
            {"account_name": "Bank", "account_type": "Cash"},
        )
        self.assertRedirects(resp, reverse("accounts:list"))
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.account_name, "Bank")

        # delete
        resp = self.client.post(reverse("accounts:delete", args=[self.acc.pk]))
        self.assertRedirects(resp, reverse("accounts:list"))
        self.acc.refresh_from_db()
        self.assertFalse(self.acc.is_active)
        self.assertTrue(Transaction.objects.filter(pk=self.tx.pk).exists())

        # restore
        resp = self.client.post(reverse("accounts:restore", args=[self.acc.pk]))
        self.assertRedirects(resp, reverse("accounts:archived"))
        self.acc.refresh_from_db()
        self.assertTrue(self.acc.is_active)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class AccountBalanceCalculationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="w", password="p")
        self.acc = Account.objects.create(account_name="Woori Bank", account_type="Banks", user=self.user)
        self.other = Account.objects.create(account_name="BDO", account_type="Banks", user=self.user)
        self.ent = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities()

        today = timezone.now().date()

        Transaction.objects.create(
            user=self.user,
            date=today,
            description="inc",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.acc,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )

        Transaction.objects.create(
            user=self.user,
            date=today,
            description="exp",
            transaction_type="expense",
            amount=Decimal("30"),
            account_source=self.acc,
            account_destination=self.out_acc,
            entity_source=self.ent,
            entity_destination=self.out_ent,
        )

        Transaction.objects.create(
            user=self.user,
            date=today,
            description="xfer out",
            transaction_type="transfer",
            amount=Decimal("20"),
            account_source=self.acc,
            account_destination=self.other,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

        Transaction.objects.create(
            user=self.user,
            date=today,
            description="xfer in",
            transaction_type="transfer",
            amount=Decimal("10"),
            account_source=self.other,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

        Transaction.objects.create(
            user=self.user,
            date=today,
            description="ignored",
            transaction_type="expense",
            amount=Decimal("999"),
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_balance_matches_running_total(self):
        self.assertEqual(self.acc.get_current_balance(), Decimal("60"))