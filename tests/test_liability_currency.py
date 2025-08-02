from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from currencies.models import Currency, ExchangeRate
from liabilities.models import CreditCard, Loan, Lender
from accounts.models import Account
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities
from decimal import Decimal

@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LiabilityCurrencyTests(TestCase):
    def setUp(self):
        self.cur_usd = Currency.objects.create(code="USD", name="US Dollar")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p", base_currency=self.cur_php)
        self.client.force_login(self.user)
        self.lender = Lender.objects.create(name="Bank")
        self.dest = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user, currency=self.cur_php)
        self.out_acc = ensure_outside_account()
        self.out_ent, self.acc_ent = ensure_fixed_entities(self.user)

        # set a KRW->PHP rate so conversions work
        self.cur_krw = Currency.objects.create(code="KRW", name="Korean Won")
        ExchangeRate.objects.create(
            currency_from=self.cur_krw,
            currency_to=self.cur_php,
            rate=Decimal("0.041"),
        )

    def test_create_credit_card_with_currency(self):
        resp = self.client.post(reverse("liabilities:credit-create"), {
            "issuer_id": self.lender.pk,
            "issuer_text": self.lender.name,
            "card_name": "Visa",
            "credit_limit": "1000",
            "interest_rate": "1",
            "statement_day": "1",
            "payment_due_day": "10",
            "currency": "USD",
        })
        self.assertEqual(resp.status_code, 302)
        card = CreditCard.objects.latest("id")
        self.assertEqual(card.currency, "USD")

    def test_create_loan_with_currency(self):
        resp = self.client.post(reverse("liabilities:loan-create"), {
            "lender_id": self.lender.pk,
            "lender_text": self.lender.name,
            "principal_amount": "500",
            "interest_rate": "1",
            "received_date": "2025-01-01",
            "term_months": "12",
            "account_destination": self.dest.pk,
            "account_source": self.out_acc.pk,
            "entity_source": self.out_ent.pk,
            "entity_destination": self.acc_ent.pk,
            "currency": "USD",
        })
        self.assertEqual(resp.status_code, 302)
        loan = Loan.objects.latest("id")
        self.assertEqual(loan.currency, "USD")

    def test_disbursement_tx_stores_currency_and_converts_display(self):
        resp = self.client.post(reverse("liabilities:loan-create"), {
            "lender_id": self.lender.pk,
            "lender_text": self.lender.name,
            "principal_amount": "5000000",
            "interest_rate": "1",
            "received_date": "2025-01-01",
            "term_months": "12",
            "account_destination": self.dest.pk,
            "account_source": self.out_acc.pk,
            "entity_source": self.out_ent.pk,
            "entity_destination": self.acc_ent.pk,
            "currency": "KRW",
        })
        self.assertEqual(resp.status_code, 302)
        loan = Loan.objects.latest("id")
        tx = loan.disbursement_tx
        self.assertEqual(tx.currency.code, "KRW")
        self.assertEqual(tx.amount, Decimal("5000000"))

        resp = self.client.get(reverse("liabilities:list"), {"tab": "loans"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "205,000.00")
        self.assertNotContains(resp, "5,000,000.00")