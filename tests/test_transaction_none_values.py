from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from transactions.models import Transaction


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class TransactionListNoneHandlingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u3", password="p")
        self.client.force_login(self.user)
        # Create a transaction without account, category or currency
        Transaction.objects.create(
            user=self.user,
            transaction_type="expense",
            amount=Decimal("10"),
        )

    def test_list_view_handles_missing_currency_and_relations(self):
        session = self.client.session
        session["display_currency"] = "PHP"  # no Currency entries exist
        session.save()
        resp = self.client.get(reverse("transactions:transaction_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "10.00")