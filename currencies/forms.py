"""Forms for managing currencies and exchange rates."""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from crispy_forms.bootstrap import FormActions

from .models import Currency, ExchangeRate, RATE_SOURCE_CHOICES


class ExchangeRateForm(forms.ModelForm):
    currency_from = forms.ModelChoiceField(
        queryset=Currency.objects.filter(is_active=True), to_field_name="code"
    )
    currency_to = forms.ModelChoiceField(
        queryset=Currency.objects.filter(is_active=True), to_field_name="code"
    )
    
    class Meta:
        model = ExchangeRate
        fields = [
            "source",
            "currency_from",
            "currency_to",
            "rate",
        ]

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop("show_actions", True)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

        layout_fields = [
            Row(
                Column("source", css_class="col-md-3"),
                Column("currency_from", css_class="col-md-3"),
                Column("currency_to", css_class="col-md-3"),
                Column("rate", css_class="col-md-3"),
                css_class="g-3",
            ),
        ]

        if show_actions:
            layout_fields.append(
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

        self.helper.layout = Layout(*layout_fields)