from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Account
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities
from liabilities.models import Lender, Loan
from transactions.models import Transaction


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class LoanDisbursementDeleteViewTests(TestCase):
    """Ensure deleting loan disbursement transactions removes the loan."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="loan", password="p")
        self.client.force_login(self.user)
        lender = Lender.objects.create(name="Bank")
        self.dest = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.out_acc = ensure_outside_account()
        self.out_ent, self.acc_ent = ensure_fixed_entities(self.user)
        self.loan = Loan.objects.create(
            user=self.user,
            lender=lender,
            principal_amount=Decimal("100"),
            interest_rate=Decimal("1"),
            received_date=date(2025, 1, 1),
            term_months=3,
        )
        self.txn = self.loan.disbursement_tx

    def test_single_delete_view(self):
        resp = self.client.post(
            reverse("transactions:transaction_delete", args=[self.txn.pk])
        )
        self.assertFalse(Loan.objects.filter(pk=self.loan.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=self.txn.pk).exists())
        storage = list(get_messages(resp.wsgi_request))
        self.assertTrue(any(m.level == messages.WARNING for m in storage))

    def test_bulk_delete_view(self):
        resp = self.client.post(
            reverse("transactions:transaction_list"),
            {"bulk-action": "delete", "selected_ids": [str(self.txn.pk)]},
        )
        self.assertFalse(Loan.objects.filter(pk=self.loan.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=self.txn.pk).exists())
        storage = list(get_messages(resp.wsgi_request))
        self.assertTrue(any(m.level == messages.WARNING for m in storage))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class LoanDisbursementSignalTests(TestCase):
    """Deleting the transaction directly should remove the loan via signal."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="sig", password="p")
        lender = Lender.objects.create(name="SigBank")
        self.dest = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.out_acc = ensure_outside_account()
        self.out_ent, self.acc_ent = ensure_fixed_entities(self.user)
        self.loan = Loan.objects.create(
            user=self.user,
            lender=lender,
            principal_amount=Decimal("50"),
            interest_rate=Decimal("1"),
            received_date=date(2025, 1, 1),
            term_months=2,
        )
        self.txn = self.loan.disbursement_tx

    def test_signal_deletes_loan(self):
        self.txn.delete()
        self.assertFalse(Loan.objects.filter(pk=self.loan.pk).exists())
