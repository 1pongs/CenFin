from decimal import Decimal
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, FormActions, Submit, Button, Div
from .models import Insurance


class InsuranceForm(forms.ModelForm):
    class Meta:
        model = Insurance
        fields = [
            "name",
            "insurance_type",
            "sum_assured",
            "premium_mode",
            "premium_amount",
            "unit_balance",
            "unit_value",
            "valuation_date",
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
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column("name", css_class="col-md-6"),
                Column("insurance_type", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("sum_assured", css_class="col-md-4"),
                Column("premium_mode", css_class="col-md-4"),
                Column("premium_amount", css_class="col-md-4"),
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