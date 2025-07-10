"""Forms for managing currencies and exchange rates."""

from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from crispy_forms.bootstrap import FormActions

from . import services

from .models import Currency, ExchangeRate, RATE_SOURCE_CHOICES


class ExchangeRateForm(forms.ModelForm):
    """Form for creating/updating :class:`ExchangeRate` instances."""

    # Use plain ChoiceFields so the list of valid options can be replaced
    # dynamically based on the selected ``source``.
    currency_from = forms.ChoiceField(choices=())
    currency_to = forms.ChoiceField(choices=())
    
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
        
        source = ""
        if self.data:
            source = (self.data.get("source") or "").upper()
        elif self.initial.get("source"):
            source = (self.initial["source"] or "").upper()
        elif self.instance.pk:
            source = self.instance.source
            
        # Load currencies from the services layer depending on the source.
        if source == "FRANKFURTER":
            data = services.get_frankfurter_currencies()
        elif source == "REM_A":
            data = services.get_rem_a_currencies()
        else:
            data = {}

        choices = [(c, f"{c} — {n}") for c, n in data.items()] if data else []

        self.fields["currency_from"].choices = choices
        self.fields["currency_to"].choices = choices
        
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

    def _get_currency(self, code: str) -> Currency:
        """Return the :class:`Currency` instance matching ``code`` or raise."""
        try:
            return Currency.objects.get(code=code)
        except Currency.DoesNotExist:
            raise forms.ValidationError(
                self.fields["currency_from"].error_messages["invalid_choice"],
                code="invalid_choice",
            )

    def clean_currency_from(self) -> Currency:
        code = self.cleaned_data.get("currency_from")
        return self._get_currency(code)

    def clean_currency_to(self) -> Currency:
        code = self.cleaned_data.get("currency_to")
        return self._get_currency(code)