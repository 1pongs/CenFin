from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from entities.models import Entity
from .models import Insurance, PremiumPayment
from acquisitions.models import Acquisition
from accounts.models import Account
from transactions.models import Transaction
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class InsuranceFlowTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.entity = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.account = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities()

    def test_insurance_creation_creates_inactive_acquisition(self):
        resp = self.client.post(reverse("insurance:create"), {
            "policy_owner": "Owner",
            "person_insured": "",
            "insurance_type": "term",
            "sum_assured": "1000",
            "premium_mode": "annual",
            "premium_amount": "100",
            "entity": self.entity.pk,
        })
        self.assertEqual(resp.status_code, 302)
        ins = Insurance.objects.get()
        self.assertEqual(ins.status, "inactive")
        self.assertIsNotNone(ins.acquisition)
        acq = ins.acquisition
        self.assertEqual(acq.status, "inactive")
        self.assertIsNone(acq.purchase_tx)

    def test_premium_payment_activates(self):
        ins_resp = self.client.post(reverse("insurance:create"), {
            "policy_owner": "Owner",
            "person_insured": "",
            "insurance_type": "term",
            "sum_assured": "1000",
            "premium_mode": "annual",
            "premium_amount": "100",
            "entity": self.entity.pk,
        })
        ins = Insurance.objects.get()

        resp = self.client.post(reverse("insurance:pay-premium", args=[ins.pk]), {
            "description": "first premium",
            "date": "2025-01-01",
            "transaction_type": "premium_payment",
            "amount": "100",
            "account_source": self.out_acc.pk,
            "account_destination": self.account.pk,
            "entity_source": self.out_ent.pk,
            "entity_destination": self.entity.pk,
        })
        self.assertEqual(resp.status_code, 302)
        ins.refresh_from_db()
        self.assertEqual(ins.status, "active")
        self.assertEqual(ins.acquisition.status, "active")
        self.assertEqual(PremiumPayment.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 1)
