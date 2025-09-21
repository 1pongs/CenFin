from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal
from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction


class TransactionImmutabilityTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.login(username="u", password="p")
        # Create accounts and entity
        self.acc = Account.objects.create(
            account_name="A", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(entity_name="E", user=self.user)
        # Create a transaction
        self.tx = Transaction.objects.create(
            user=self.user,
            date="2020-01-01",
            description="t",
            transaction_type="expense",
            amount=Decimal("100.00"),
            account_source=self.acc,
            account_destination=None,
            entity_source=self.ent,
            entity_destination=None,
        )

    def test_amount_preserved_on_update_when_disabled(self):
        url = reverse("transactions:transaction_edit", args=[self.tx.pk])
        # GET to get form; amount should be disabled in the UI, but we'll
        # simulate a POST attempting to change the amount and assert the
        # server preserved the original.
        self.client.post(
            url,
            {
                "date": "2020-01-01",
                "description": "t-upd",
                "transaction_type": "expense",
                "amount": "999.00",
                "account_source": str(self.acc.pk),
                "account_destination": "",
                "entity_source": str(self.ent.pk),
                "entity_destination": "",
                "remarks": "",
                "save": "Save",
            },
            follow=True,
        )
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.amount, Decimal("100.00"))
        self.assertEqual(self.tx.description, "t-upd")
