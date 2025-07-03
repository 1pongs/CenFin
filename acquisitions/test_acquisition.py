from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from django.contrib.auth import get_user_model
from .models import Acquisition
from .forms import AcquisitionForm, SellAcquisitionForm


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AcquisitionListViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="viewer", password="p")
        self.client.force_login(self.user)

    def test_list_view_uses_template(self):
        resp = self.client.get(reverse("acquisitions:acquisition-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "acquisitions/acquisition_list.html")

    def test_search_filters_by_name(self):
        tx1 = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="a",
            transaction_type="buy acquisition",
            amount=Decimal("1"),
        )
        tx2 = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="b",
            transaction_type="buy acquisition",
            amount=Decimal("1"),
        )
        Acquisition.objects.create(
            name="Alpha",
            category="product",
            purchase_tx=tx1,
            user=self.user,
            status="active",
        )
        Acquisition.objects.create(
            name="Beta",
            category="product",
            purchase_tx=tx2,
            user=self.user,
            status="active",
        )
        resp = self.client.get(reverse("acquisitions:acquisition-list"), {"q": "alp"})
        self.assertContains(resp, "Alpha")
        self.assertNotContains(resp, "Beta")

    def test_insurance_acquisitions_are_excluded(self):
        buy_tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="ins",
            transaction_type="buy acquisition",
            amount=Decimal("1"),
        )
        Acquisition.objects.create(
            name="Policy",
            category="insurance",
            purchase_tx=buy_tx,
            user=self.user,
        )
        resp = self.client.get(reverse("acquisitions:acquisition-list"))
        self.assertNotContains(resp, "Policy")

@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
)
class AcquisitionTransactionAmountTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")
        self.client.force_login(self.user)
        self.acc_src = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.acc_dest = Account.objects.create(
            account_name="AssetAcc", account_type="Others", user=self.user
        )
        self.ent_src = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
        self.ent_dest = Entity.objects.create(
            entity_name="Vendor", entity_type="outside", user=self.user
        )

        self.buy_tx = Transaction.objects.create(
            date=timezone.now().date(),
            description="Buy Piglet",
            transaction_type="buy acquisition",
            amount=Decimal("6000"),
            account_source=self.acc_src,
            account_destination=self.acc_dest,
            entity_source=self.ent_src,
            entity_destination=self.ent_dest,
            user=self.user,
        )
        self.acquisition = Acquisition.objects.create(
            name="Piglet", category="product", purchase_tx=self.buy_tx, user=self.user
        )

    def test_sell_transaction_amount_is_difference(self):
        response = self.client.post(
            reverse("acquisitions:sell", args=[self.acquisition.pk]),
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

        self.acquisition.refresh_from_db()
        sell_tx = self.acquisition.sell_tx
        self.assertIsNotNone(sell_tx)
        self.assertEqual(sell_tx.amount, Decimal("4000"))

        #buy transaction plus two sale-related transactions should exist
        self.assertEqual(Transaction.objects.count(), 3)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AcquisitionFormBalanceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u2", password="p")
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Vendor", entity_type="personal fund", user=self.user
        )
        self.out_acc = Account.objects.create(
            account_name="Outside", account_type="Outside", user=self.user
        )
        from entities.utils import ensure_fixed_entities

        self.out_ent, _ = ensure_fixed_entities(self.user)

    def _form_data(self, **overrides):
        data = {
            "name": "Item",
            "category": "product",
            "date": timezone.now().date(),
            "amount": "50",
            "account_source": self.acc.pk,
            "account_destination": self.acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        data.update(overrides)
        return data

    def test_balance_validation(self):
        form = AcquisitionForm(data=self._form_data(amount="50"), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("account_source", form.errors)
        self.assertIn("entity_source", form.errors)

    def test_outside_allowed(self):
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.acc,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )
        form = AcquisitionForm(
            data=self._form_data(account_source=self.out_acc.pk, amount="50"),
            user=self.user,
        )
        self.assertTrue(form.is_valid())

        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed2",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.acc,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )
        form = AcquisitionForm(
            data=self._form_data(entity_source=self.out_ent.pk, amount="50"),
            user=self.user,
        )
        self.assertTrue(form.is_valid())


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AcquisitionComputedFieldsTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u3", password="p")
        self.acc_src = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.acc_dest = Account.objects.create(
            account_name="Invest", account_type="Others", user=self.user
        )
        self.ent_src = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
        self.ent_dest = Entity.objects.create(
            entity_name="Market", entity_type="outside", user=self.user
        )

        self.buy_tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="Buy Cow",
            transaction_type="buy acquisition",
            amount=Decimal("600"),
            account_source=self.acc_src,
            account_destination=self.acc_dest,
            entity_source=self.ent_src,
            entity_destination=self.ent_dest,
        )
        self.acquisition = Acquisition.objects.create(
            name="Cow", category="product", purchase_tx=self.buy_tx, user=self.user
        )

    def test_computed_fields_none_when_unsold(self):
        self.assertIsNone(self.acquisition.selling_date)
        self.assertIsNone(self.acquisition.price_sold)
        self.assertIsNone(self.acquisition.profit)

    def test_computed_fields_after_sale(self):
        sale_date = timezone.now().date()
        self.client.force_login(self.user)
        self.client.post(
            reverse("acquisitions:sell", args=[self.acquisition.pk]),
            {
                "date": sale_date,
                "sale_price": "1000",
                "account_source": self.acc_dest.pk,
                "account_destination": self.acc_src.pk,
                "entity_source": self.ent_dest.pk,
                "entity_destination": self.ent_src.pk,
            },
        )

        self.acquisition.refresh_from_db()
        self.assertEqual(self.acquisition.selling_date, sale_date)
        self.assertEqual(self.acquisition.price_sold, Decimal("1000"))
        self.assertEqual(self.acquisition.profit, Decimal("400"))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class OutsideAccountVisibilityTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="vis", password="p")
        self.cash = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        from accounts.utils import ensure_outside_account

        self.outside = ensure_outside_account()

    def test_acquisition_form_includes_outside(self):
        form = AcquisitionForm(user=self.user)
        qs = form.fields["account_source"].queryset
        self.assertIn(self.outside, qs)
        self.assertIn(self.outside, form.fields["account_destination"].queryset)


class AcquisitionFormValidationTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="vtest", password="p")

    def test_vehicle_future_model_year_invalid(self):
        form = AcquisitionForm(
            data={
                "name": "Car",
                "category": "vehicle",
                "date": timezone.now().date(),
                "amount": "1",
                "account_source": Account.objects.create(
                    account_name="A", account_type="Cash", user=self.user
                ).pk,
                "account_destination": Account.objects.create(
                    account_name="B", account_type="Cash", user=self.user
                ).pk,
                "entity_source": Entity.objects.create(
                    entity_name="E", entity_type="outside", user=self.user
                ).pk,
                "entity_destination": Entity.objects.create(
                    entity_name="E2", entity_type="outside", user=self.user
                ).pk,
                "model_year": timezone.now().year + 1,
            },
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("model_year", form.errors)

    def test_term_insurance_cash_value_zeroed(self):
        form = AcquisitionForm(user=self.user)
        choices = [c[0] for c in form.fields["category"].choices]
        self.assertNotIn("insurance", choices)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class OutsideAutoLockTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="lock", password="p")
        self.cash = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.dest = Account.objects.create(
            account_name="Dest", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Vendor", entity_type="personal fund", user=self.user
        )
        from accounts.utils import ensure_outside_account
        from entities.utils import ensure_fixed_entities

        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)

    def test_buy_form_forces_outside_destination(self):
        form = AcquisitionForm(
            data={
                "name": "Thing",
                "category": "product",
                "date": timezone.now().date(),
                "amount": "10",
                "account_source": self.out_acc.pk,
                "account_destination": self.dest.pk,
                "entity_source": self.out_ent.pk,
                "entity_destination": self.ent.pk,
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["account_destination"], self.out_acc)

    def test_sell_form_forces_outside_source(self):
        form = SellAcquisitionForm(
            data={
                "date": timezone.now().date(),
                "sale_price": "5",
                "account_source": self.dest.pk,
                "account_destination": self.cash.pk,
                "entity_source": self.ent.pk,
                "entity_destination": self.ent.pk,
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["account_source"], self.out_acc)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AcquisitionAverageHelpersTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="avg", password="p")
        self.account = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.entity = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="buy acquisition",
            amount=Decimal("100"),
            account_source=self.account,
            account_destination=self.account,
            entity_source=self.entity,
            entity_destination=self.entity,
        )
        self.acq = Acquisition.objects.create(
            name="Item",
            category="product",
            purchase_tx=self.tx,
            user=self.user,
            quantity=Decimal("1"),
            avg_unit_cost=Decimal("100"),
            status="active",
        )

    def test_recompute_average(self):
        self.acq.recompute_average(Decimal("1"), Decimal("200"))
        self.acq.refresh_from_db()
        self.assertEqual(self.acq.quantity, Decimal("2"))
        self.assertEqual(self.acq.avg_unit_cost, Decimal("150"))

    def test_sell_marks_inactive(self):
        self.acq.sell(Decimal("1"), Decimal("50"), self.account, timezone.now().date())
        self.acq.refresh_from_db()
        self.assertEqual(self.acq.quantity, Decimal("0"))
        self.assertEqual(self.acq.status, "inactive")
        self.assertEqual(Transaction.objects.count(), 3)