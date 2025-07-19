from decimal import Decimal
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Account
from entities.models import Entity
from .models import Transaction
from .forms import TransactionForm
from transactions.models import TransactionTemplate
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities


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
            transaction_type="buy acquisition",
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
        self.assertEqual(field.choices, [("buy acquisition", "Buy Acquisition")])

    def test_new_form_excludes_asset_types(self):
        form = TransactionForm(user=self.user)
        choices = [c[0] for c in form.fields["transaction_type"].choices]
        self.assertNotIn("buy acquisition", choices)
        self.assertNotIn("sell acquisition", choices)

    def test_property_types_removed(self):
        form = TransactionForm(user=self.user)
        choices = [c[0] for c in form.fields["transaction_type"].choices]
        self.assertNotIn("buy property", choices)
        self.assertNotIn("sell property", choices)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionFormBalanceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="t", password="p")
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Vendor", entity_type="personal fund", user=self.user)
        self.out_acc = Account.objects.create(account_name="Outside", account_type="Outside", user=self.user)
        from entities.utils import ensure_fixed_entities
        self.out_ent, _ = ensure_fixed_entities(self.user)

    def _form_data(self, **overrides):
        data = {
            "date": timezone.now().date(),
            "description": "Test",
            "transaction_type": "income",
            "amount": "50",
            "account_source": self.acc.pk,
            "account_destination": self.acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        data.update(overrides)
        return data

    def test_insufficient_balance_shows_errors(self):
        form = TransactionForm(data=self._form_data(transaction_type="transfer", amount="50"), user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("account_source", form.errors)
        self.assertIn("entity_source", form.errors)

    def test_outside_skips_balance_check(self):
        # deposit funds to the other side so validation can pass
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.out_acc,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )
        form = TransactionForm(data=self._form_data(account_source=self.out_acc.pk, amount="50"), user=self.user)
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
            entity_destination=self.out_ent,
        )
        form = TransactionForm(data=self._form_data(entity_source=self.out_ent.pk, amount="50"), user=self.user)
        self.assertTrue(form.is_valid())

    def test_income_auto_sets_outside(self):
        data = self._form_data(transaction_type="income")
        form = TransactionForm(data=data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["account_source"].account_name, "Outside")
        self.assertEqual(form.cleaned_data["entity_source"].entity_name, "Outside")

    def test_expense_auto_sets_outside(self):
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
        data = self._form_data(transaction_type="expense")
        form = TransactionForm(data=data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["account_destination"].account_name, "Outside")
        self.assertEqual(form.cleaned_data["entity_destination"].entity_name, "Outside")


class OutsideEnforcedTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="z", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Vendor", entity_type="personal fund", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)

    def _post_txn(self, tx_type, **overrides):
        data = {
            "date": timezone.now().date(),
            "description": "t",
            "transaction_type": tx_type,
            "amount": "10",
            "account_source": self.acc.pk,
            "account_destination": self.acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        data.update(overrides)
        return self.client.post(reverse("transactions:transaction_create"), data)

    def test_income_enforced(self):
        resp = self._post_txn("income")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 1)
        tx = Transaction.objects.first()
        self.assertEqual(tx.account_source, self.out_acc)
        self.assertEqual(tx.entity_source, self.out_ent)

    def test_expense_enforced(self):
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
        resp = self._post_txn("expense")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 2)
        tx = Transaction.objects.order_by("-id").first()
        self.assertEqual(tx.account_destination, self.out_acc)
        self.assertEqual(tx.entity_destination, self.out_ent)


class TemplateOutsideEnforcedTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="q", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(account_name="Cash", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="Vendor", entity_type="personal fund", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)

    def _post_tpl(self, tx_type):
        data = {
            "name": "tpl",
            "transaction_type": tx_type,
            "account_source": self.acc.pk,
            "account_destination": self.acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        return self.client.post(reverse("transactions:template_create"), data)

    def test_income_template_enforced(self):
        resp = self._post_tpl("income")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TransactionTemplate.objects.count(), 1)
        tpl = TransactionTemplate.objects.first()
        self.assertEqual(tpl.autopop_map["account_source"], self.out_acc.pk)
        self.assertEqual(tpl.autopop_map["entity_source"], self.out_ent.pk)

    def test_expense_template_enforced(self):
        resp = self._post_tpl("expense")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TransactionTemplate.objects.count(), 1)
        tpl = TransactionTemplate.objects.first()
        self.assertEqual(tpl.autopop_map["account_destination"], self.out_acc.pk)
        self.assertEqual(tpl.autopop_map["entity_destination"], self.out_ent.pk)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ConstantsTest(TestCase):
    def test_credit_constants(self):
        from .constants import transaction_type_TX_MAP, ASSET_TYPE_CHOICES
        self.assertEqual(
            transaction_type_TX_MAP["cc_purchase"],
            ("expense", "outside", "credit", "outside"),
        )
        self.assertEqual(
            transaction_type_TX_MAP["cc_payment"],
            ("transfer", "transfer", "liquid", "credit"),
        )
        self.assertIn(("credit", "Credit"), ASSET_TYPE_CHOICES)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class HiddenTypesTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ht", password="p")

    def test_hidden_types_removed(self):
        form = TransactionForm(user=self.user)
        offered = {c[0] for c in form.fields["transaction_type"].choices}
        hidden = {
            "premium_payment", "loan_disbursement",
            "loan_repayment", "cc_purchase", "cc_payment"
        }
        self.assertEqual(len(hidden & offered), 0)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class LoanTxnImmutableTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="imm", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(account_name="A", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="E", entity_type="outside", user=self.user)
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            transaction_type="loan_disbursement",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_fields_disabled(self):
        from django.urls import reverse
        resp = self.client.get(reverse("transactions:transaction_update", args=[self.tx.pk]))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertTrue(all(f.disabled for f in form.fields.values()))

    def test_post_denied(self):
        from django.urls import reverse
        resp = self.client.post(
            reverse("transactions:transaction_update", args=[self.tx.pk]),
            {"amount": "20"},
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class AcquisitionTxnImmutableTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="imm2", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(account_name="A", account_type="Cash", user=self.user)
        self.ent = Entity.objects.create(entity_name="E", entity_type="outside", user=self.user)
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            transaction_type="buy acquisition",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )

    def test_fields_disabled(self):
        from django.urls import reverse
        resp = self.client.get(reverse("transactions:transaction_update", args=[self.tx.pk]))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertTrue(all(f.disabled for f in form.fields.values()))

    def test_post_denied(self):
        from django.urls import reverse
        resp = self.client.post(
            reverse("transactions:transaction_update", args=[self.tx.pk]),
            {"amount": "20"},
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class TransactionCurrencyAutoTest(TestCase):
    def setUp(self):
        from currencies.models import Currency
        User = get_user_model()
        self.cur_usd = Currency.objects.create(code="USD", name="US Dollar")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.user = User.objects.create_user(username="c", password="p")
        self.account = Account.objects.create(
            account_name="Wallet", account_type="Cash", user=self.user, currency=self.cur_usd
        )
        self.dest = Account.objects.create(
            account_name="Bank", account_type="Cash", user=self.user, currency=self.cur_php
        )
        self.ent = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("10"),
            account_source=self.out_acc,
            account_destination=self.account,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )

    def test_form_sets_currency_from_account(self):
        form = TransactionForm(
            data={
                "date": timezone.now().date(),
                "description": "t",
                "transaction_type": "transfer",
                "amount": "5",
                "account_source": self.account.pk,
                "account_destination": self.dest.pk,
                "entity_source": self.ent.pk,
                "entity_destination": self.ent.pk,
            },
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertEqual(tx.currency, self.account.currency)


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class CrossCurrencyHiddenTxTest(TestCase):
    def setUp(self):
        from currencies.models import Currency
        User = get_user_model()
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.user = User.objects.create_user(username="h", password="p")
        self.client.force_login(self.user)
        self.src_acc = Account.objects.create(
            account_name="Woori", account_type="Cash", user=self.user, currency=self.cur_krw
        )
        self.dest_acc = Account.objects.create(
            account_name="BDO", account_type="Cash", user=self.user, currency=self.cur_php
        )
        self.ent = Entity.objects.create(entity_name="Me", entity_type="outside", user=self.user)
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed",
            transaction_type="income",
            amount=Decimal("2000"),
            account_source=self.out_acc,
            account_destination=self.src_acc,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )

    def test_hidden_transactions_created(self):
        data = {
            "date": timezone.now().date(),
            "description": "x",
            "transaction_type": "transfer",
            "amount": "1000",
            "destination_amount": "50",
            "account_source": self.src_acc.pk,
            "account_destination": self.dest_acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        resp = self.client.post(reverse("transactions:transaction_create"), data)
        self.assertEqual(resp.status_code, 302)

        parent = Transaction.objects.order_by("-id").first()
        hidden = Transaction.all_objects.filter(parent_transfer=parent)
        self.assertEqual(hidden.count(), 2)
        codes = {t.currency.code for t in hidden}
        self.assertEqual(codes, {"KRW", "PHP"})
