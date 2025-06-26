from decimal import Decimal
from datetime import date
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from transactions.models import Transaction
from .models import Lender, Loan, LoanPayment


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
