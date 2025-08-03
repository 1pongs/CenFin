from decimal import Decimal

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
    account_source = forms.ModelChoiceField(queryset=Account.objects.all(), required=False)
    account_destination = forms.ModelChoiceField(queryset=Account.objects.all(), required=False)
    entity_source = forms.ModelChoiceField(queryset=Entity.objects.all(), required=False)
    entity_destination = forms.ModelChoiceField(queryset=Entity.objects.all(), required=False)
    remarks = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.locked_entity = kwargs.pop("locked_entity", None)
        super().__init__(*args, **kwargs)

        css = self.fields["amount"].widget.attrs.get("class", "")
        self.fields["amount"].widget.attrs["class"] = f"{css} amount-input".strip()
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
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.label_class = "fw-semibold"
        self.helper.field_class = "mb-2"
        self.helper.layout = Layout(
            Row(
                Column("name", css_class="col-md-6"),
                Column("category", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("date", css_class="col-md-6"),
                Column("amount", css_class="col-md-6"),
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

        if acc and acc.account_name != "Outside":
            if acc.current_balance() < amt:
                self.add_error("account_source", f"Insufficient funds in {acc}.")

        if ent and ent.entity_name != "Outside":
            if ent.current_balance() < amt:
                self.add_error("entity_source", f"Insufficient funds in {ent}.")

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
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column("date", css_class="col-md-6"),
                Column("sale_price", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source", css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("entity_source", css_class="col-md-6"),
                Column("entity_destination", css_class="col-md-6"),
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