from decimal import Decimal
from datetime import date
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from transactions.models import Transaction
from .models import Lender, Loan, LoanPayment, CreditCard
from django.core.exceptions import ValidationError
from accounts.models import Account
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities


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


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class CreditCardFormTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="card", password="p")
        self.client.force_login(self.user)
        self.lender = Lender.objects.create(name="BDO")

    def _post_card(self, **overrides):
        from django.urls import reverse
        data = {
            "issuer_id": overrides.get("issuer_id", ""),
            "issuer_text": overrides.get("issuer_text", ""),
            "card_name": overrides.get("card_name", "Visa"),
            "credit_limit": overrides.get("credit_limit", "1000"),
            "interest_rate": overrides.get("interest_rate", "1"),
            "statement_day": overrides.get("statement_day", "1"),
            "payment_due_day": overrides.get("payment_due_day", "10"),
        }
        return self.client.post(reverse("liabilities:credit-create"), data)

    def test_missing_issuer_shows_error(self):
        resp = self._post_card()
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertFormError(form, "issuer_text", "Issuer is required — select one or create a new issuer first.")

    def test_new_issuer_created(self):
        resp = self._post_card(issuer_text="NewBank")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Lender.objects.filter(name="NewBank").exists())
        card = CreditCard.objects.latest("id")
        self.assertEqual(card.issuer.name, "NewBank")

    def test_duplicate_name_error(self):
        resp = self._post_card(issuer_text="bdo")
        self.assertEqual(resp.status_code, 302)
        card = CreditCard.objects.latest("id")
        self.assertEqual(card.issuer, self.lender)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LoanPaymentTransactionTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="pay", password="p")
        self.client.force_login(self.user)
        self.lender = Lender.objects.create(name="BDO")
        self.cash = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, self.acc_ent = ensure_fixed_entities(self.user)
        self.loan = Loan.objects.create(
            user=self.user,
            lender=self.lender,
            principal_amount=Decimal("300"),
            interest_rate=Decimal("1"),
            received_date=date(2025, 1, 1),
            term_months=3,
        )
        Transaction.objects.create(
            user=self.user,
            date=date(2025, 1, 1),
            transaction_type="income",
            amount=Decimal("500"),
            account_destination=self.cash,
            entity_source=self.out_ent,
            entity_destination=self.acc_ent,
        )

    def _post(self, amount):
        data = {
            "date": "2025-02-01",
            "description": "Pay",
            "transaction_type": "transfer",
            "amount": str(amount),
            "account_source": self.cash.pk,
            "account_destination": self.out_acc.pk,
            "entity_source": self.acc_ent.pk,
            "entity_destination": self.out_ent.pk,
            "loan_id": self.loan.pk,
        }
        return self.client.post(reverse("transactions:transaction_create"), data)

    def test_overpayment_rejected_and_balance_updated(self):
        resp = self._post(400)
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertIn("amount", form.errors)

        resp = self._post(100)
        self.assertEqual(resp.status_code, 302)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.outstanding_balance, Decimal("200"))