from decimal import Decimal
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from transactions.forms import TransactionForm
from transactions.models import CategoryTag, Transaction
from accounts.models import Account
from entities.models import Entity
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class CategoryTagScopeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.entity = Entity.objects.create(entity_name="Vendor", entity_type="personal fund", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.acc,
            entity_source=self.out_ent,
            entity_destination=self.entity,
        )

    def _form_data(self, **overrides):
        data = {
            "date": timezone.now().date(),
            "description": "t",
            "transaction_type": "expense",
            "amount": "30",
            "account_source": self.acc.pk,
            "account_destination": self.out_acc.pk,
            "entity_source": self.entity.pk,
            "entity_destination": self.out_ent.pk,
            "category_names": "Food",
        }
        data.update(overrides)
        return data

    def test_save_categories_scopes_account(self):
        form = TransactionForm(data=self._form_data(), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        tag = CategoryTag.objects.get(name="Food")
        self.assertEqual(tag.account, self.acc)
        self.assertIn(tag, tx.categories.all())

    def test_tag_list_includes_account_and_global(self):
        CategoryTag.objects.create(user=self.user, transaction_type="expense", name="Global")
        CategoryTag.objects.create(user=self.user, transaction_type="expense", name="Fuel", account=self.acc)
        url = reverse("transactions:tags") + f"?transaction_type=expense&account={self.acc.pk}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        names = {t["name"] for t in resp.json()}
        self.assertEqual(names, {"Global", "Fuel"})

    def test_global_uniqueness(self):
        CategoryTag.objects.create(user=self.user, transaction_type="expense", name="Food")
        dup = CategoryTag(user=self.user, transaction_type="expense", name="Food")
        with self.assertRaises(ValidationError):
            dup.full_clean()

    def test_entity_summary_endpoint(self):
        # expense created in setUp via _form_data
        form = TransactionForm(data=self._form_data(), user=self.user)
        form.is_valid()
        form.save()
        income_data = self._form_data(
            transaction_type="income",
            amount="70",
            account_source=self.out_acc.pk,
            account_destination=self.acc.pk,
            entity_source=self.out_ent.pk,
            entity_destination=self.entity.pk,
            category_names="Salary",
        )
        form = TransactionForm(data=income_data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        url = reverse("transactions:entity_category_summary", args=[self.entity.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        summary = {d["categories__name"]: d["total"] for d in resp.json()}
        self.assertEqual(summary["Food"], "30")
        self.assertEqual(summary["Salary"], "70")
