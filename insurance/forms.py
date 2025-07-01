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
            "provider",
            "insurance_type",
            "sum_assured",
            "premium_mode",
            "premium_amount",
            "maturity_date",
            "unit_balance",
            "unit_value",
            "valuation_date",
            "entity",
            "acquisition",
        ]
        widgets = {
            "valuation_date": forms.DateInput(attrs={"type": "date"}),
            "maturity_date": forms.DateInput(attrs={"type": "date"}),
            "sum_assured": forms.TextInput(attrs={"inputmode": "decimal"}),
            "premium_amount": forms.TextInput(attrs={"inputmode": "decimal"}),
            "unit_balance": forms.TextInput(attrs={"inputmode": "decimal"}),
            "unit_value": forms.TextInput(attrs={"inputmode": "decimal"}),
        }

    def __init__(self, *args, show_actions=True, **kwargs):
        """Initialize form and optionally hide action buttons.

        Parameters
        ----------
        show_actions : bool, optional
            If ``False`` the layout will omit the ``FormActions`` section.  This
            is useful when the form is embedded inside a modal that provides its
            own buttons.
        """
        super().__init__(*args, **kwargs)
        for fld in ["sum_assured", "premium_amount", "unit_balance", "unit_value"]:
            if fld in self.fields:
                css = self.fields[fld].widget.attrs.get("class", "")
                self.fields[fld].widget.attrs["class"] = f"{css} amount-input".strip()
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.Select):
                base = w.attrs.get("class", "form-select")
                w.attrs["class"] = f"{base} form-select-sm"
            elif not isinstance(w, forms.HiddenInput):
                base = w.attrs.get("class", "form-control")
                w.attrs["class"] = f"{base} form-control-sm"
        for fld in ["entity", "acquisition"]:
            if fld in self.fields:
                self.fields[fld].widget = forms.HiddenInput()
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.label_class = "fw-semibold"
        self.helper.field_class = "mb-2"
        layout_items = [
            Row(
                Column("policy_owner", css_class="col-md-6"),
                Column("person_insured", css_class="col-md-6"),
                css_class="g-2",
            ),
            Row(
                Column("provider", css_class="col-md-6"),
                Column("maturity_date", css_class="col-md-6"),
                css_class="g-2",
            ),
            Row(
                Column("insurance_type", css_class="col-md-6"),
                Column("sum_assured", css_class="col-md-6"),
                css_class="g-2",
            ),
            Row(
                Column("premium_mode", css_class="col-md-6"),
                Column("premium_amount", css_class="col-md-6"),
                css_class="g-2",
            ),
            Div(
                Row(
                    Column("unit_balance", css_class="col-md-4"),
                    Column("unit_value", css_class="col-md-4"),
                    Column("valuation_date", css_class="col-md-4"),
                    css_class="g-2",
                ),
                css_id="vul-fields",
            ),
        ]
        if show_actions:
            layout_items.append(
                FormActions(
                    Submit("save", "Save", css_class="btn btn-primary"),
                    Button(
                        "cancel",
                        "Cancel",
                        css_class="btn btn-outline-secondary",
                        onclick="history.back()",
                    ),
                    css_class="d-flex justify-content-end gap-2 mt-3",
                )
            )

        self.helper.layout = Layout(*layout_items)


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