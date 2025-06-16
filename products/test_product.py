from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity
from transactions.models import Transaction
from django.contrib.auth import get_user_model
from .models import Product
from .forms import ProductForm, SellProductForm

# Create your tests here.

@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
)
class ProductTransactionAmountTest(TestCase):
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
            transaction_type="buy product",
            amount=Decimal("6000"),
            account_source=self.acc_src,
            account_destination=self.acc_dest,
            entity_source=self.ent_src,
            entity_destination=self.ent_dest,
            user=self.user,
        )
        self.product = Product.objects.create(name="Piglet", purchase_tx=self.buy_tx, user=self.user)

    def test_sell_transaction_amount_is_difference(self):
        response = self.client.post(
            reverse("products:sell", args=[self.product.pk]),
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

        self.product.refresh_from_db()
        sell_tx = self.product.sell_tx
        self.assertIsNotNone(sell_tx)
        self.assertEqual(sell_tx.amount, Decimal("4000"))

        # only buy and sell transactions should exist
        self.assertEqual(Transaction.objects.count(), 2)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class ProductFormBalanceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u2", password="p")
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Vendor", entity_type="others", user=self.user)
        self.out_acc = Account.objects.create(account_name="Outside", account_type="Outside", user=self.user)
        self.out_ent = Entity.objects.create(entity_name="Outside", entity_type="outside", user=self.user)

    def _form_data(self, **overrides):
        data = {
            "name": "Product",
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
        form = ProductForm(data=self._form_data(amount="50"), user=self.user)
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
        form = ProductForm(data=self._form_data(account_source=self.out_acc.pk, amount="50"), user=self.user)
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
        form = ProductForm(data=self._form_data(entity_source=self.out_ent.pk, amount="50"), user=self.user)
        self.assertTrue(form.is_valid())


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ProductComputedFieldsTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u3", password="p")
        self.acc_src = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.acc_dest = Account.objects.create(account_name="Invest", account_type="Others", user=self.user)
        self.ent_src = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.ent_dest = Entity.objects.create(entity_name="Market", entity_type="outside", user=self.user)

        self.buy_tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="Buy Cow",
            transaction_type="buy product",
            amount=Decimal("600"),
            account_source=self.acc_src,
            account_destination=self.acc_dest,
            entity_source=self.ent_src,
            entity_destination=self.ent_dest,
        )
        self.product = Product.objects.create(name="Cow", purchase_tx=self.buy_tx, user=self.user)

    def test_computed_fields_none_when_unsold(self):
        self.assertIsNone(self.product.selling_date)
        self.assertIsNone(self.product.price_sold)
        self.assertIsNone(self.product.profit)

    def test_computed_fields_after_sale(self):
        sale_date = timezone.now().date()
        self.client.force_login(self.user)
        self.client.post(
            reverse("products:sell", args=[self.product.pk]),
            {
                "date": sale_date,
                "sale_price": "1000",
                "account_source": self.acc_dest.pk,
                "account_destination": self.acc_src.pk,
                "entity_source": self.ent_dest.pk,
                "entity_destination": self.ent_src.pk,
            },
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.selling_date, sale_date)
        self.assertEqual(self.product.price_sold, Decimal("1000"))
        self.assertEqual(self.product.profit, Decimal("400"))


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class OutsideAccountVisibilityTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="vis", password="p")
        self.cash = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.outside = Account.objects.get(account_name="Outside", user=None)

    def test_product_form_includes_outside(self):
        form = ProductForm(user=self.user)
        qs = form.fields["account_source"].queryset
        self.assertIn(self.outside, qs)
        self.assertIn(self.outside, form.fields["account_destination"].queryset)

    def test_sell_form_includes_outside(self):
        form = SellProductForm(user=self.user)
        qs = form.fields["account_source"].queryset
        self.assertIn(self.outside, qs)
        self.assertIn(self.outside, form.fields["account_destination"].queryset)