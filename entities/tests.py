from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from entities.models import Entity
from accounts.models import Account
from transactions.models import Transaction


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class EntitySoftDeleteTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="test",
            transaction_type="transfer",
            amount=Decimal("5"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_edit_delete_restore_entity(self):
        resp = self.client.post(
            reverse("entities:edit", args=[self.ent.pk]),
            {"entity_name": "You", "entity_type": "outside"},
        )
        self.assertRedirects(resp, reverse("entities:list"))
        self.ent.refresh_from_db()
        self.assertEqual(self.ent.entity_name, "You")

        resp = self.client.post(reverse("entities:delete", args=[self.ent.pk]))
        self.assertRedirects(resp, reverse("entities:list"))
        self.ent.refresh_from_db()
        self.assertFalse(self.ent.is_active)
        self.assertTrue(Transaction.objects.filter(pk=self.tx.pk).exists())

        resp = self.client.post(reverse("entities:restore", args=[self.ent.pk]))
        self.assertRedirects(resp, reverse("entities:archived"))
        self.ent.refresh_from_db()
        self.assertTrue(self.ent.is_active)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class OutsideHiddenListTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="x", password="p")
        self.client.force_login(self.user)
        Entity.objects.create(entity_name="Mine", entity_type="others", user=self.user)
        self.outside = Entity.objects.get(entity_name="Outside", user=None)

    def test_outside_not_in_list(self):
        resp = self.client.get(reverse("entities:list"))
        self.assertEqual(resp.status_code, 200)
        names = [e["the_name"] for e in resp.context["entities"]]
        self.assertNotIn("Outside", names)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class AccountHiddenListTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="y", password="p")
        self.client.force_login(self.user)
        Entity.objects.create(entity_name="Mine", entity_type="others", user=self.user)
        from entities.utils import ensure_fixed_entities
        _, self.account_ent = ensure_fixed_entities()

    def test_account_not_in_list(self):
        resp = self.client.get(reverse("entities:list"))
        self.assertEqual(resp.status_code, 200)
        names = [e["the_name"] for e in resp.context["entities"]]
        self.assertNotIn("Account", names)