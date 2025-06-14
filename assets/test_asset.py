from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from django.contrib.auth import get_user_model
from .models import Asset

# Create your tests here.

@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
)
class AssetTransactionAmountTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")
        self.client.force_login(self.user)
        self.acc_src = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.acc_dest = Account.objects.create(account_name="AssetAcc", account_type="Others", user=self.user)
        self.ent_src = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.ent_dest = Entity.objects.create(entity_name="Vendor", entity_type="outside", user=self.user)

        self.buy_tx = Transaction.objects.create(
            date=timezone.now().date(),
            description="Buy Piglet",
            transaction_type="buy asset",
            amount=Decimal("6000"),
            account_source=self.acc_src,
            account_destination=self.acc_dest,
            entity_source=self.ent_src,
            entity_destination=self.ent_dest,
            user=self.user,
        )
        self.asset = Asset.objects.create(name="Piglet", purchase_tx=self.buy_tx, user=self.user)

    def test_sell_transaction_amount_is_difference(self):
        response = self.client.post(
            reverse("assets:sell", args=[self.asset.pk]),
            {
                "date": timezone.now().date(),
                "sale_price": "10000",
                "account_source": self.acc_dest.pk,
                "account_destination": self.acc_src.pk,
                "entity_source": self.ent_dest.pk,
                "entity_destination": self.ent_src.pk,
            },
        )
        self.assertEqual(response.status_code, 302)

        self.asset.refresh_from_db()
        sell_tx = self.asset.sell_tx
        self.assertIsNotNone(sell_tx)
        self.assertEqual(sell_tx.amount, Decimal("4000"))

        # only buy and sell transactions should exist
        self.assertEqual(Transaction.objects.count(), 2)