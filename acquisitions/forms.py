from decimal import Decimal

from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Column, Layout, Row, Submit
from django import forms
from django.db.models import Q
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity
from currencies.models import Currency


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
    currency = forms.ModelChoiceField(queryset=Currency.objects.none(), required=False)
    account_source = forms.ModelChoiceField(queryset=Account.objects.all(), required=False)
    account_destination = forms.ModelChoiceField(queryset=Account.objects.all(), required=False)
    entity_source = forms.ModelChoiceField(queryset=Entity.objects.all(), required=False)
    entity_destination = forms.ModelChoiceField(queryset=Entity.objects.all(), required=False)
    remarks = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    # stock/bond
    current_value = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    market = forms.CharField(max_length=100, required=False)
    expected_lifespan_years = forms.IntegerField(
        required=False, label="Expected lifespan (yrs)"
    )
    location = forms.CharField(max_length=120, required=False)

    # universal
    target_selling_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )

    # vehicle
    mileage = forms.IntegerField(required=False, min_value=0, label="Mileage (km)")
    plate_number = forms.CharField(max_length=20, required=False)
    model_year = forms.IntegerField(required=False, label="Model Year")

    # property
    expected_lifespan_years = forms.IntegerField(required=False)
    location = forms.CharField(max_length=255, required=False)

    # insurance
    insurance_type = forms.ChoiceField(
        choices=[
            ("vul", "VUL"),
            ("term", "Term"),
            ("whole", "Whole"),
            ("health", "Health"),
        ],
        required=False,
    )
    sum_assured_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    cash_value = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    maturity_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    provider = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.locked_entity = kwargs.pop("locked_entity", None)
        super().__init__(*args, **kwargs)

        for fld in ["amount", "current_value", "cash_value", "sum_assured_amount"]:
            if fld in self.fields:
                css = self.fields[fld].widget.attrs.get("class", "")
                self.fields[fld].widget.attrs["class"] = f"{css} amount-input".strip()
        self.fields["currency"].queryset = Currency.objects.filter(is_active=True)
        if user and getattr(user, "base_currency_id", None):
            self.fields["currency"].initial = user.base_currency
        else:
            first = self.fields["currency"].queryset.first()
            if first:
                self.fields["currency"].initial = first
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
                Column("date", css_class="col-md-4"),
                Column("amount", css_class="col-md-4"),
                Column("currency", css_class="col-md-4"),
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
                Column("current_value", css_class="col-md-6"),
                Column("market", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("expected_lifespan_years", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("location", css_class="col-md-6"),
                Column("target_selling_date", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("insurance_type", css_class="col-md-6"),
                Column("cash_value", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("sum_assured_amount", css_class="col-md-6"),
                Column("maturity_date", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("provider", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("mileage", css_class="col-md-4"),
                Column("plate_number", css_class="col-md-4"),
                Column("model_year", css_class="col-md-4"),
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

        cat = cleaned.get("category")
        if cat in ("vehicle", "equipment"):
            model_year = cleaned.get("model_year")
            if model_year and model_year > timezone.now().year:
                self.add_error("model_year", "Model year cannot be in the future")
            mileage = cleaned.get("mileage")
            if mileage is not None and mileage < 0:
                self.add_error("mileage", "Mileage must be zero or positive")

        if cat == "insurance":
            if not cleaned.get("sum_assured_amount"):
                self.add_error("sum_assured_amount", "This field is required.")
            if cleaned.get("insurance_type") == "term":
                cleaned["cash_value"] = 0

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