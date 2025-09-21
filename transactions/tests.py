from decimal import Decimal
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Account
from entities.models import Entity
from currencies.models import Currency
from django.core.exceptions import ValidationError
from .models import Transaction, CategoryTag
from .forms import TransactionForm, TemplateForm
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
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
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
        form = TransactionForm(
            data=self._form_data(transaction_type="transfer", amount="50"),
            user=self.user,
        )
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
        form = TransactionForm(
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
            entity_destination=self.out_ent,
        )
        form = TransactionForm(
            data=self._form_data(entity_source=self.out_ent.pk, amount="50"),
            user=self.user,
        )
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
        self.assertEqual(
            form.cleaned_data["account_destination"].account_name, "Outside"
        )
        self.assertEqual(form.cleaned_data["entity_destination"].entity_name, "Outside")

    def test_income_excludes_outside_destination(self):
        data = self._form_data(transaction_type="income")
        form = TransactionForm(data=data, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        acc_names = list(
            form.fields["account_destination"].queryset.values_list(
                "account_name", flat=True
            )
        )
        ent_names = list(
            form.fields["entity_destination"].queryset.values_list(
                "entity_name", flat=True
            )
        )
        self.assertNotIn("Outside", acc_names)
        self.assertNotIn("Outside", ent_names)

    def test_edit_skips_insufficient_balance_check(self):
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
        tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="spend",
            transaction_type="expense",
            amount=Decimal("50"),
            account_source=self.acc,
            account_destination=self.out_acc,
            entity_source=self.ent,
            entity_destination=self.out_ent,
        )
        data = self._form_data(transaction_type="expense", amount="80")
        form = TransactionForm(data=data, instance=tx, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)


class OutsideEnforcedTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="z", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Vendor", entity_type="personal fund", user=self.user
        )
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


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionDeleteReversalTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="d", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.out_acc = ensure_outside_account()
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="personal fund", user=self.user
        )
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
            entity_destination=self.ent,
        )
        self.tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="spend",
            transaction_type="expense",
            amount=Decimal("40"),
            account_source=self.acc,
            account_destination=self.out_acc,
            entity_source=self.ent,
            entity_destination=self.out_ent,
        )

    def test_delete_creates_reversal_and_hides_original(self):
        self.client.get(reverse("transactions:transaction_delete", args=[self.tx.pk]))
        orig = Transaction.all_objects.get(pk=self.tx.pk)
        self.assertTrue(orig.is_hidden)
        # Reversal rows are hidden by default and should not appear in the
        # visible manager.
        rev_visible = Transaction.objects.filter(
            description__icontains="Reversal",
            account_destination=self.acc,
            account_source=self.out_acc,
        ).first()
        self.assertIsNone(rev_visible)
        # But they should be discoverable via include_reversals() helper or
        # via all_objects.
        rev = Transaction.all_objects.filter(
            description__icontains="Reversal",
            account_destination=self.acc,
            account_source=self.out_acc,
        ).first()
        self.assertIsNotNone(rev)
        self.assertEqual(rev.amount, Decimal("40"))
        # And include_reversals() should also find the reversal
        rev2 = (
            Transaction.objects.include_reversals()
            .filter(
                description__icontains="Reversal",
                account_destination=self.acc,
                account_source=self.out_acc,
            )
            .first()
        )
        self.assertIsNotNone(rev2)
        self.assertEqual(rev2.pk, rev.pk)

    def test_undo_delete_removes_reversal_and_restores_original(self):
        # Delete to create reversal rows
        self.client.get(reverse("transactions:transaction_delete", args=[self.tx.pk]))
        orig = Transaction.all_objects.get(pk=self.tx.pk)
        self.assertTrue(orig.is_hidden)
        # Find reversal rows
        revs = Transaction.all_objects.filter(reversed_transaction=orig)
        self.assertTrue(revs.exists())
        # Undo restore via the view
        resp = self.client.get(
            reverse("transactions:transaction_undo_delete", args=[orig.pk])
        )
        self.assertEqual(resp.status_code, 302)
        restored = Transaction.objects.filter(pk=orig.pk).first()
        self.assertIsNotNone(restored)
        self.assertFalse(restored.is_hidden)
        # Reversals should be deleted
        revs_after = Transaction.all_objects.filter(reversed_transaction=orig)
        self.assertFalse(revs_after.exists())


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class BulkDeleteGuardTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="bd", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.out_acc = ensure_outside_account()
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="personal fund", user=self.user
        )
        self.out_ent, _ = ensure_fixed_entities(self.user)
        # Seed balance 100
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
        # Two expenses of 70 and 20; deleting 70 alone would overdraw later 20, but
        # deleting both together is safe; our batch guard should allow both together.
        self.tx_big = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="big spend",
            transaction_type="expense",
            amount=Decimal("70"),
            account_source=self.acc,
            account_destination=self.out_acc,
            entity_source=self.ent,
            entity_destination=self.out_ent,
        )
        self.tx_small = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="small spend",
            transaction_type="expense",
            amount=Decimal("20"),
            account_source=self.acc,
            account_destination=self.out_acc,
            entity_source=self.ent,
            entity_destination=self.out_ent,
        )

    def test_bulk_delete_allows_joint_safe_deletions(self):
        url = reverse("transactions:transaction_list")
        resp = self.client.post(
            url,
            {
                "bulk-action": "delete",
                "selected_ids": [str(self.tx_big.pk), str(self.tx_small.pk)],
            },
        )
        self.assertEqual(resp.status_code, 302)
        # Both should be hidden after reversal
        big = Transaction.all_objects.get(pk=self.tx_big.pk)
        small = Transaction.all_objects.get(pk=self.tx_small.pk)
        self.assertTrue(big.is_hidden)
        self.assertTrue(small.is_hidden)
        # Visible queryset should only include the seed income
        self.assertEqual(Transaction.objects.count(), 1)


class TemplateOutsideEnforcedTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="q", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Vendor", entity_type="personal fund", user=self.user
        )
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

    def test_income_template_excludes_outside_destination(self):
        form = TemplateForm(data={"transaction_type": "income"}, user=self.user)
        acc_names = list(
            form.fields["account_destination"].queryset.values_list(
                "account_name", flat=True
            )
        )
        ent_names = list(
            form.fields["entity_destination"].queryset.values_list(
                "entity_name", flat=True
            )
        )
        self.assertNotIn("Outside", acc_names)
        self.assertNotIn("Outside", ent_names)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
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


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class HiddenTypesTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="ht", password="p")

    def test_hidden_types_removed(self):
        form = TransactionForm(user=self.user)
        offered = {c[0] for c in form.fields["transaction_type"].choices}
        hidden = {
            "premium_payment",
            "loan_disbursement",
            "loan_repayment",
            "cc_purchase",
            "cc_payment",
        }
        self.assertEqual(len(hidden & offered), 0)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class SellAcquisitionCategoryMappingTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="map", password="p")
        self.acc = Account.objects.create(
            account_name="Cash", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="Piggery", entity_type="personal fund", user=self.user
        )
        # create a transfer-scoped tag for this entity (sell -> transfer mapping)
        self.transfer_tag = CategoryTag.objects.create(
            user=self.user, name="Sales", transaction_type="transfer", entity=self.ent
        )

    def test_sell_acquisition_uses_income_tags_for_category_queryset(self):
        # Build form data where transaction_type is sell_acquisition and entity destination is the entity
        form = TransactionForm(
            data={
                "transaction_type": "sell_acquisition",
                "entity_destination": self.ent.pk,
            },
            user=self.user,
        )
        # The category queryset should include the transfer_tag created above
        qs = form.fields["category"].queryset
        self.assertIn(self.transfer_tag, list(qs))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class LoanTxnImmutableTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="imm", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="A", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="E", entity_type="outside", user=self.user
        )
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

        resp = self.client.get(
            reverse("transactions:transaction_update", args=[self.tx.pk])
        )
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


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class AcquisitionTxnImmutableTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="imm2", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="A", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="E", entity_type="outside", user=self.user
        )
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

        resp = self.client.get(
            reverse("transactions:transaction_update", args=[self.tx.pk])
        )
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        # Only transaction_type should be disabled for acquisition txns
        disabled = {name for name, f in form.fields.items() if getattr(f, 'disabled', False)}
        self.assertIn("transaction_type", disabled)
        # other common editable fields should not be disabled
        for editable in ("description", "date", "amount", "remarks", "category"):
            self.assertIn(editable, form.fields)
            self.assertFalse(getattr(form.fields[editable], "disabled", False))

    def test_post_denied(self):
        from django.urls import reverse

        # Posting edits to acquisition txns should be allowed; after save
        # we expect a redirect (status 302). Create an acquisition that
        # references this transaction and verify redirect target.
        from acquisitions.models import Acquisition

        acq = Acquisition.objects.create(
            name="X",
            category="product",
            purchase_tx=self.tx,
            status="active",
            user=self.user,
        )
        # Use the special Outside account for the destination so the
        # 'buy acquisition' transaction_type is permitted by the form.
        out_acc = ensure_outside_account()
        resp = self.client.post(
            reverse("transactions:transaction_update", args=[self.tx.pk]),
            {
                "date": timezone.now().date(),
                "description": "edited",
                "transaction_type": "buy acquisition",
                "amount": "20",
                "account_source": self.acc.pk,
                "account_destination": out_acc.pk,
                "entity_source": self.ent.pk,
                "entity_destination": self.ent.pk,
            },
        )
        # Expect redirect to the acquisition detail page
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("acquisitions:acquisition-detail", args=[acq.pk]), resp.url)


class AcquisitionDeleteRestrictionTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="del", password="p")
        self.client.force_login(self.user)
        self.acc = Account.objects.create(
            account_name="A", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="E", entity_type="outside", user=self.user
        )
        # create purchase and sell txns and link to an Acquisition
        self.purchase = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="buy",
            transaction_type="buy acquisition",
            amount=Decimal("10"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        self.profit = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="profit",
            transaction_type="income",
            amount=Decimal("2"),
            account_source=self.acc,
            account_destination=self.acc,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        from acquisitions.models import Acquisition

        self.acq = Acquisition.objects.create(
            name="Y",
            category="product",
            purchase_tx=self.purchase,
            sell_tx=self.profit,
            status="active",
            user=self.user,
        )

    def test_cannot_delete_single_acquisition_leg(self):
        resp = self.client.get(reverse("transactions:transaction_delete", args=[self.purchase.pk]))
        # Expect redirect to acquisition detail with an error message
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("acquisitions:acquisition-detail", args=[self.acq.pk]), resp.url)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionCurrencyAutoTest(TestCase):
    def setUp(self):
        from currencies.models import Currency

        User = get_user_model()
        self.cur_usd = Currency.objects.create(code="USD", name="US Dollar")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.user = User.objects.create_user(username="c", password="p")
        self.account = Account.objects.create(
            account_name="Wallet",
            account_type="Cash",
            user=self.user,
            currency=self.cur_usd,
        )
        self.dest = Account.objects.create(
            account_name="Bank",
            account_type="Cash",
            user=self.user,
            currency=self.cur_php,
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
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


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class CrossCurrencyHiddenTxTest(TestCase):
    def setUp(self):
        from currencies.models import Currency

        User = get_user_model()
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.user = User.objects.create_user(username="h", password="p")
        self.client.force_login(self.user)
        self.src_acc = Account.objects.create(
            account_name="Woori",
            account_type="Cash",
            user=self.user,
            currency=self.cur_krw,
        )
        self.dest_acc = Account.objects.create(
            account_name="BDO",
            account_type="Cash",
            user=self.user,
            currency=self.cur_php,
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
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
        count_before = Transaction.objects.count()
        resp = self.client.post(reverse("transactions:transaction_create"), data)
        self.assertEqual(resp.status_code, 302)

        self.assertEqual(Transaction.objects.count(), count_before + 1)
        parent = Transaction.objects.order_by("-id").first()
        self.assertFalse(parent.is_hidden)
        self.assertEqual(parent.amount, Decimal("1000"))
        self.assertEqual(parent.currency, self.cur_krw)
        self.assertEqual(parent.destination_amount, Decimal("50"))
        hidden = Transaction.all_objects.filter(is_hidden=True, parent_transfer=parent)
        self.assertEqual(hidden.count(), 2)
        codes = {t.currency.code for t in hidden}
        self.assertEqual(codes, {"KRW", "PHP"})
        dest_tx = hidden.filter(currency=self.cur_php).first()
        self.assertEqual(dest_tx.amount, Decimal("50"))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class RemittanceEditTests(TestCase):
    def setUp(self):
        from currencies.models import Currency

        User = get_user_model()
        self.cur_krw = Currency.objects.create(code="KRW", name="Won")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        self.user = User.objects.create_user(username="e", password="p")
        self.client.force_login(self.user)
        self.src_acc = Account.objects.create(
            account_name="Woori",
            account_type="Cash",
            user=self.user,
            currency=self.cur_krw,
        )
        self.dest_acc = Account.objects.create(
            account_name="BDO",
            account_type="Cash",
            user=self.user,
            currency=self.cur_php,
        )
        self.ent = Entity.objects.create(
            entity_name="Me", entity_type="outside", user=self.user
        )
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
        self.client.post(reverse("transactions:transaction_create"), data)
        self.parent = Transaction.objects.order_by("-id").first()

    def test_edit_form_prefills_amounts(self):
        resp = self.client.get(
            reverse("transactions:transaction_update", args=[self.parent.pk])
        )
        form = resp.context["form"]
        self.assertEqual(form.initial["amount"], Decimal("1000"))
        self.assertEqual(form.initial["destination_amount"], Decimal("50"))

    def test_update_recreates_hidden_children(self):
        data = {
            "date": self.parent.date,
            "description": "x",
            "transaction_type": "transfer",
            "amount": "1000",
            "destination_amount": "60",
            "account_source": self.src_acc.pk,
            "account_destination": self.dest_acc.pk,
            "entity_source": self.ent.pk,
            "entity_destination": self.ent.pk,
        }
        resp = self.client.post(
            reverse("transactions:transaction_update", args=[self.parent.pk]), data
        )
        self.assertEqual(resp.status_code, 302)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.amount, Decimal("1000"))
        self.assertEqual(self.parent.destination_amount, Decimal("60"))
        hidden = Transaction.all_objects.filter(parent_transfer=self.parent)
        self.assertEqual(hidden.count(), 2)
        outflow = hidden.filter(account_source=self.src_acc).first()
        inflow = hidden.filter(account_destination=self.dest_acc).first()
        self.assertEqual(outflow.amount, Decimal("1000"))
        self.assertEqual(inflow.amount, Decimal("60"))
        self.assertEqual(inflow.destination_amount, Decimal("60"))


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class TransactionCurrencyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cur", password="p")
        self.cur1 = Currency.objects.create(code="USD")
        self.cur2 = Currency.objects.create(code="EUR")
        self.acc1 = Account.objects.create(
            account_name="A1", account_type="Cash", user=self.user, currency=self.cur1
        )
        self.acc2 = Account.objects.create(
            account_name="A2", account_type="Cash", user=self.user, currency=self.cur2
        )
        self.ent = Entity.objects.create(
            entity_name="Vendor", entity_type="personal fund", user=self.user
        )

    def test_mismatched_account_currencies_invalid(self):
        tx = Transaction(
            user=self.user,
            date=timezone.now().date(),
            description="x",
            transaction_type="expense",
            amount=Decimal("1"),
            account_source=self.acc1,
            account_destination=self.acc2,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        with self.assertRaises(ValidationError):
            tx.full_clean()

    def test_account_currency_change_does_not_affect_tx(self):
        acc_same = Account.objects.create(
            account_name="B", account_type="Cash", user=self.user, currency=self.cur1
        )
        tx = Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="y",
            transaction_type="expense",
            amount=Decimal("5"),
            account_source=acc_same,
            account_destination=acc_same,
            entity_source=self.ent,
            entity_destination=self.ent,
        )
        self.assertEqual(tx.currency, self.cur1)
        acc_same.currency = self.cur2
        acc_same.save()
        tx.refresh_from_db()
        self.assertEqual(tx.currency, self.cur1)


@override_settings(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
)
class PairBalanceViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="pb", password="p")
        self.client.force_login(self.user)
        self.acc1 = Account.objects.create(
            account_name="A1", account_type="Cash", user=self.user
        )
        self.acc2 = Account.objects.create(
            account_name="A2", account_type="Cash", user=self.user
        )
        self.ent = Entity.objects.create(
            entity_name="E", entity_type="personal fund", user=self.user
        )
        self.out_acc = ensure_outside_account()
        self.out_ent, _ = ensure_fixed_entities(self.user)
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed1",
            transaction_type="income",
            amount=Decimal("100"),
            account_source=self.out_acc,
            account_destination=self.acc1,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )
        Transaction.objects.create(
            user=self.user,
            date=timezone.now().date(),
            description="seed2",
            transaction_type="income",
            amount=Decimal("200"),
            account_source=self.out_acc,
            account_destination=self.acc2,
            entity_source=self.out_ent,
            entity_destination=self.ent,
        )

    def test_pair_balance_specific_account(self):
        url = reverse("transactions:pair_balance")
        resp = self.client.get(url, {"account": self.acc1.pk, "entity": self.ent.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(Decimal(data["balance"]), Decimal("100"))
