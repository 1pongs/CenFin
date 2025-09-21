from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from liabilities.models import Lender
from accounts.models import Account


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AccountNameReuseTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.lender = Lender.objects.create(name="ReuseBank")
        self.client.force_login(self.user)

    def _post_card(self, name="Woori Card"):
        data = {
            "issuer_id": self.lender.pk,
            "issuer_text": self.lender.name,
            "card_name": name,
            "credit_limit": "1000",
            "interest_rate": "1",
            "statement_day": "1",
            "payment_due_day": "10",
        }
        return self.client.post(reverse("liabilities:credit-create"), data)

    def test_inactive_account_reused(self):
        acc = Account.objects.create(
            account_name="Woori Card", account_type="Cash", user=self.user
        )
        acc.delete()
        resp = self._post_card()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Account.objects.filter(
                account_name="Woori Card", user=self.user, is_active=True
            ).count(),
            1,
        )

    def test_active_account_conflict(self):
        Account.objects.create(
            account_name="Woori Card", account_type="Cash", user=self.user
        )
        resp = self._post_card()
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertIn("card_name", form.errors)

    def test_soft_delete_then_readd_single_active(self):
        acc = Account.objects.create(
            account_name="Woori Card", account_type="Cash", user=self.user
        )
        acc.delete()
        resp = self._post_card()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            Account.objects.filter(
                account_name="Woori Card", user=self.user, is_active=True
            ).count(),
            1,
        )
        self.assertEqual(
            Account.objects.filter(account_name="Woori Card", user=self.user).count(), 1
        )
