from decimal import Decimal
from datetime import date
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Account
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities
from liabilities.models import Lender, Loan


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LoanAutocompleteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.lender = Lender.objects.create(name="Welcome Bank")
        self.dest = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, self.acc_ent = ensure_fixed_entities(self.user)

    def _form_data(self, **overrides):
        data = {
            "lender_id": overrides.get("lender_id", ""),
            "lender_text": overrides.get("lender_text", ""),
            "principal_amount": overrides.get("principal_amount", "100"),
            "interest_rate": overrides.get("interest_rate", "1"),
            "received_date": overrides.get("received_date", "2025-01-01"),
            "term_months": overrides.get("term_months", "12"),
            "account_destination": self.dest.pk,
            "account_source": self.out_acc.pk,
            "entity_source": self.out_ent.pk,
            "entity_destination": self.acc_ent.pk,
        }
        return data

    def test_existing_lender_allows_second_loan(self):
        Loan.objects.create(
            user=self.user,
            lender=self.lender,
            principal_amount=Decimal("50"),
            interest_rate=Decimal("1"),
            received_date=date(2025, 1, 1),
            term_months=6,
        )
        resp = self.client.post(reverse("liabilities:loan-create"), self._form_data(lender_id=self.lender.pk))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Loan.objects.filter(lender=self.lender).count(), 2)

    def test_autocomplete_search_json(self):
        resp = self.client.get(reverse("ajax_lender_search"), {"q": "Wel"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"results": [{"id": self.lender.pk, "text": "Welcome Bank"}]})

    def test_new_lender_created_via_ajax(self):
        resp = self.client.post(reverse("ajax_lender_create"), {"name": "Zigzag Bank"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Lender.objects.filter(name="Zigzag Bank").exists())
