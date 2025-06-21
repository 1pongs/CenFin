from decimal import Decimal
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button, Div
from crispy_forms.bootstrap import FormActions
from .models import Insurance
from transactions.forms import TransactionForm
from accounts.models import Account
from entities.models import Entity
from django.db.models import Sum, F, Value, DecimalField, Q
from django.db.models.functions import Coalesce


class InsuranceForm(forms.ModelForm):
    class Meta:
        model = Insurance
        fields = [
            "policy_owner",
            "person_insured",
            "insurance_type",
            "sum_assured",
            "premium_mode",
            "premium_amount",
            "unit_balance",
            "unit_value",
            "valuation_date",
            "entity",
            "acquisition",
        ]
        widgets = {
            "valuation_date": forms.DateInput(attrs={"type": "date"}),
            "sum_assured": forms.TextInput(attrs={"inputmode": "decimal"}),
            "premium_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
            "unit_balance": forms.TextInput(attrs={"inputmode": "decimal"}),
            "unit_value": forms.TextInput(attrs={"inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fld in ["sum_assured", "premium_amount", "unit_balance", "unit_value"]:
            if fld in self.fields:
                css = self.fields[fld].widget.attrs.get("class", "")
                self.fields[fld].widget.attrs["class"] = f"{css} amount-input".strip()
        for fld in ["entity", "acquisition"]:
            if fld in self.fields:
                self.fields[fld].widget = forms.HiddenInput()
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column("insurance_type", css_class="col-md-6"),
                Column("premium_mode", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("policy_owner", css_class="col-md-6"),
                Column("person_insured", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("sum_assured", css_class="col-md-6"),
                Column("premium_amount", css_class="col-md-6"),
                css_class="g-3",
            ),
            Div(
                Row(
                    Column("unit_balance", css_class="col-md-4"),
                    Column("unit_value", css_class="col-md-4"),
                    Column("valuation_date", css_class="col-md-4"),
                    css_class="g-3",
                ),
                css_id="vul-fields",
            ),
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


class PremiumPaymentForm(TransactionForm):
    """Simplified transaction form for paying insurance premiums."""

    class Meta(TransactionForm.Meta):
        exclude = ["template"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # remove template field completely
        self.fields.pop("template", None)

        user = getattr(self, "user", None)
        if user is not None:
            # annotate account and entity balances
            acc_qs = (
                Account.objects.filter(Q(user=user) | Q(user__isnull=True), is_active=True)
                .with_current_balance()
            )
            self.fields["account_source"].queryset = acc_qs

            ent_qs = (
                Entity.objects.filter(Q(user=user) | Q(user__isnull=True), is_active=True)
                .annotate(
                    inflow=Coalesce(
                        Sum(
                            "transaction_entity_destination__amount",
                            filter=Q(
                                transaction_entity_destination__asset_type_destination__iexact="liquid"
                            ),
                        ),
                        Value(Decimal("0"), output_field=DecimalField()),
                    ),
                    outflow=Coalesce(
                        Sum(
                            "transaction_entity_source__amount",
                            filter=Q(
                                transaction_entity_source__asset_type_source__iexact="liquid"
                            ),
                        ),
                        Value(Decimal("0"), output_field=DecimalField()),
                    ),
                )
                .annotate(balance=F("inflow") - F("outflow"))
            )
            self.fields["entity_source"].queryset = ent_qs

            # format labels with balances
            self.fields["account_source"].label_from_instance = (
                lambda obj: f"{obj.account_name} (₱ {obj.current_balance:,.2f})"
            )
            self.fields["entity_source"].label_from_instance = (
                lambda obj: f"{obj.entity_name} (₱ {obj.balance:,.2f})"
            )

        # rebuild layout without template field
        self.helper.layout = Layout(
            Row(Column("description", css_class="col-md-6"), css_class="g-3"),
            Row(
                Column("date", css_class="col-md-6"),
                Column("transaction_type", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(Column("category_names", css_class="col-md-6"), css_class="g-3"),
            Row(Column("amount", css_class="col-md-6"), css_class="g-3"),
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