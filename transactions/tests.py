from decimal import Decimal
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model

from accounts.models import Account
from entities.models import Entity
from .models import Transaction
from .forms import TransactionForm


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionFormAssetTypeTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="test",
            transaction_type="buy asset",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_editing_asset_transaction_shows_read_only_choice(self):
        form = TransactionForm(instance=self.tx, user=self.user)
        field = form.fields["transaction_type"]
        self.assertTrue(field.disabled)
        self.assertEqual(field.choices, [("buy asset", "Buy Asset")])

    def test_new_form_excludes_asset_types(self):
        form = TransactionForm(user=self.user)
        choices = [c[0] for c in form.fields["transaction_type"].choices]
        self.assertNotIn("buy asset", choices)
        self.assertNotIn("sell asset", choices)
