from decimal import Decimal
from datetime import date
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from transactions.models import Transaction
from .models import Lender, Loan, LoanPayment
from django.core.exceptions import ValidationError


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LoanModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="bor", password="p")
        self.lender = Lender.objects.create(name="BDO")

    def test_create_loan_generates_payments_and_tx(self):
        loan = Loan.objects.create(
            user=self.user,
            lender=self.lender,
            principal_amount=Decimal("1000"),
            interest_rate=Decimal("5"),
            received_date=date(2025, 1, 1),
            term_months=3,
        )
        self.assertEqual(LoanPayment.objects.filter(loan=loan).count(), 3)
        self.assertEqual(loan.outstanding_balance, Decimal("1000"))
        self.assertEqual(Transaction.objects.filter(transaction_type="loan_disbursement").count(), 1)

    def test_mark_payment_updates_balance(self):
        loan = Loan.objects.create(
            user=self.user,
            lender=self.lender,
            principal_amount=Decimal("300"),
            interest_rate=Decimal("5"),
            received_date=date(2025, 1, 1),
            term_months=3,
        )
        payment = loan.payments.first()
        tx = Transaction.objects.create(
            user=self.user,
            date=date(2025, 2, 1),
            transaction_type="loan_repayment",
            amount=payment.amount,
        )
        payment.mark_paid(tx)
        loan.refresh_from_db()
        self.assertTrue(payment.is_paid)
        self.assertEqual(loan.outstanding_balance, Decimal("200"))


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LiabilityListViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="view", password="p")
        self.client.force_login(self.user)

    def test_list_view_uses_template(self):
        from django.urls import reverse
        resp = self.client.get(reverse("liabilities:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "liabilities/liability_list.html")

    def test_list_view_renders_nav_tabs_and_filters(self):
        from django.urls import reverse
        resp = self.client.get(reverse("liabilities:list"))
        self.assertContains(resp, "navbar-dark")
        self.assertContains(resp, '<a class="nav-link active" href="?tab=credit">Credit</a>', html=True)
        self.assertContains(resp, 'id="filter-form"')


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LenderUniqueTest(TestCase):
    def test_lender_name_unique_case_insensitive(self):
        Lender.objects.create(name="Test Bank")
        with self.assertRaises(ValidationError):
            Lender.objects.create(name="test bank")