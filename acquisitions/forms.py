from decimal import Decimal, ROUND_HALF_UP

from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Column, Layout, Row, Submit
from django import forms
from django.db.models import Q
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity


class AcquisitionForm(forms.Form):
    name = forms.CharField(max_length=255)
    category = forms.ChoiceField(
        choices=[
            ("product", "Product"),
            ("stock_bond", "Stock/Bond"),
            ("property", "Property"),
            ("equipment", "Equipment"),
            ("vehicle", "Vehicle"),
        ]
    )
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    account_source = forms.ModelChoiceField(
        queryset=Account.objects.all(), required=False
    )
    account_destination = forms.ModelChoiceField(
        queryset=Account.objects.all(), required=False
    )
    entity_source = forms.ModelChoiceField(
        queryset=Entity.objects.all(), required=False
    )
    entity_destination = forms.ModelChoiceField(
        queryset=Entity.objects.all(), required=False
    )
    remarks = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.locked_entity = kwargs.pop("locked_entity", None)
        # support disabling amount edits when view wants immutable amounts
        self._disable_amount = kwargs.pop("disable_amount", False)
        super().__init__(*args, **kwargs)

        css = self.fields["amount"].widget.attrs.get("class", "")
        self.fields["amount"].widget.attrs["class"] = f"{css} amount-input".strip()
        if user is not None:
            acct_qs = Account.objects.filter(
                Q(user=user) | Q(user__isnull=True),
                is_active=True,
                system_hidden=False,
            ).exclude(account_name__istartswith="Remittance")
            ent_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            self.fields["account_source"].queryset = acct_qs
            self.fields["account_destination"].queryset = acct_qs
            self.fields["entity_source"].queryset = ent_qs
            self.fields["entity_destination"].queryset = ent_qs

        # always lock destination to the special Outside account
        try:
            self.outside_account = Account.objects.get(
                account_name="Outside", user__isnull=True
            )
            self.fields["account_destination"].initial = self.outside_account
            self.fields["account_destination"].disabled = True
            self.fields["account_destination"].required = False
        except Account.DoesNotExist:
            self.outside_account = None

        if self.locked_entity is not None:
            self.fields["entity_destination"].initial = self.locked_entity
            self.fields["entity_destination"].disabled = True
            # Default entity_source to the same locked entity unless user changes it
            try:
                if not self.fields["entity_source"].initial:
                    self.fields["entity_source"].initial = self.locked_entity
            except Exception:
                pass
        # If amount edits are disabled (update flows), mark widget disabled
        if getattr(self, "_disable_amount", False):
            try:
                self.fields["amount"].disabled = True
            except Exception:
                pass
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.label_class = "fw-semibold"
        self.helper.field_class = "mb-2"
        self.helper.layout = Layout(
            # Ask for entities/accounts before category/amount
            Row(
                Column("name", css_class="col-md-6"),
                Column("date", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("entity_source", css_class="col-md-6"),
                Column("entity_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source", css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("category", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("amount", css_class="col-md-6"),
                css_class="g-3",
            ),
            "remarks",
            FormActions(
                Submit("save", "Save", css_class="btn btn-primary"),
                Button(
                    "cancel",
                    "Cancel",
                    css_class="btn btn-outline-secondary",
                    onclick="history.back()",
                ),
                css_class="d-flex justify-content-end gap-2 mt-3",
            ),
        )

    def clean(self):
        cleaned = super().clean()
        amt = cleaned.get("amount") or Decimal("0")
        acc = cleaned.get("account_source")
        ent = cleaned.get("entity_source")
        # If the view locked an entity (via URL param) and the user didn't
        # select an entity_source, default it to the locked one so the
        # pair-balance logic applies consistently.
        if (not ent) and getattr(self, "locked_entity", None) is not None:
            ent = self.locked_entity
            cleaned["entity_source"] = ent

        # Compare at cent precision so exact-balance spends are allowed
        amt_c = Decimal(str(amt)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Prepare account balance once for reuse
        bal_acc_c = None
        if acc and acc.account_name != "Outside":
            try:
                bal = acc.get_current_balance() or Decimal("0")
            except Exception:
                bal = acc.current_balance() or Decimal("0")
            bal_acc_c = Decimal(str(bal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Prefer pair/entity sufficiency first when an entity is selected
        if ent and ent.entity_name != "Outside":
            try:
                from cenfin_proj.utils import get_account_entity_balance
            except Exception:
                get_account_entity_balance = None  # type: ignore

            pair_bal = Decimal("0")
            if acc and get_account_entity_balance:
                try:
                    pair_bal = Decimal(str(get_account_entity_balance(acc.id, ent.id)))
                except Exception:
                    pair_bal = Decimal("0")
            try:
                ent_liquid = ent.current_balance() or Decimal("0")
            except Exception:
                ent_liquid = Decimal("0")

            pair_c = Decimal(str(pair_bal)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ent_c = Decimal(str(ent_liquid)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # If the pair OR the entity has enough funds, allow without raising
            if pair_c >= amt_c or ent_c >= amt_c:
                pass
            else:
                # Neither pair nor entity has enough. If the account is also
                # insufficient, flag BOTH fields to match historical tests.
                if bal_acc_c is None or bal_acc_c < amt_c:
                    if acc and acc.account_name != "Outside":
                        self.add_error("account_source", f"Insufficient funds in {acc}.")
                    # Always flag the entity too when its liquidity/pair is short
                    self.add_error("entity_source", f"Insufficient funds in {ent}.")
                else:
                    # Account can cover but entity/pair cannot — attribute to entity
                    self.add_error("entity_source", f"Insufficient funds in {ent}.")
        else:
            # No entity chosen — fall back to plain account-level guard
            if bal_acc_c is not None and bal_acc_c < amt_c:
                self.add_error("account_source", f"Insufficient funds in {acc}.")

        if self.locked_entity is not None:
            cleaned["entity_destination"] = self.locked_entity

        if self.outside_account is not None:
            cleaned["account_destination"] = self.outside_account

        return cleaned


class SellAcquisitionForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=lambda: timezone.now().date(),
    )
    sale_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    account_source = forms.ModelChoiceField(queryset=Account.objects.all())
    account_destination = forms.ModelChoiceField(queryset=Account.objects.all())
    entity_source = forms.ModelChoiceField(queryset=Entity.objects.all())
    entity_destination = forms.ModelChoiceField(queryset=Entity.objects.all())
    remarks = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        css = self.fields["sale_price"].widget.attrs.get("class", "")
        self.fields["sale_price"].widget.attrs["class"] = f"{css} amount-input".strip()
        if user is not None:
            acct_qs = Account.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            ent_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            self.fields["account_source"].queryset = acct_qs
            self.fields["account_destination"].queryset = acct_qs
            self.fields["entity_source"].queryset = ent_qs
            self.fields["entity_destination"].queryset = ent_qs
        try:
            self.outside_account = Account.objects.get(
                account_name="Outside", user__isnull=True
            )
            self.fields["account_source"].initial = self.outside_account
            self.fields["account_source"].disabled = True
            self.fields["account_source"].required = False
        except Account.DoesNotExist:
            self.outside_account = None
        # Disable sale_price editing when requested (update flows)
        if getattr(self, "_disable_amount", False):
            try:
                self.fields["sale_price"].disabled = True
            except Exception:
                pass
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            # Entities/accounts first, then amount
            Row(
                Column("date", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("entity_source", css_class="col-md-6"),
                Column("entity_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source", css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("sale_price", css_class="col-md-6"),
                css_class="g-3",
            ),
            "remarks",
            FormActions(
                Submit("sell", "Sell", css_class="btn btn-primary"),
                Button(
                    "cancel",
                    "Cancel",
                    css_class="btn btn-outline-secondary",
                    onclick="history.back()",
                ),
                css_class="d-flex justify-content-end gap-2 mt-3",
            ),
        )

    def clean(self):
        cleaned = super().clean()
        if self.outside_account is not None:
            cleaned["account_source"] = self.outside_account
        return cleaned
