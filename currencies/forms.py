"""Forms for managing currencies and exchange rates."""

from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from crispy_forms.bootstrap import FormActions

from . import services

from .models import Currency, ExchangeRate, RATE_SOURCE_CHOICES


class ExchangeRateForm(forms.ModelForm):
    """Form for creating/updating :class:`ExchangeRate` instances."""
    
    error_messages = {"invalid_choice": _("Select a valid currency code.")}

    # Use simple CharFields so we can rebuild the <select> options
    # dynamically every time the form is instantiated.
    currency_from = forms.CharField(widget=forms.Select())
    currency_to = forms.CharField(widget=forms.Select())
    
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
        
        source_raw = (self.data.get("source") or getattr(self.instance, "source", "")).upper()
        currency_map = (
            services.get_frankfurter_currencies() if source_raw == "FRANKFURTER"
            else services.get_rem_a_currencies() if source_raw == "REM_A"
            else {}
        )
        choices = [(c, f"{c} — {n}") for c, n in currency_map.items()] or [("", "None")]
        self.currency_map = currency_map
        self.fields["currency_from"].widget.choices = choices
        self.fields["currency_to"].widget.choices = choices
        
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
                self.error_messages["invalid_choice"],
                code="invalid_choice",
            )

    def clean(self):
        cleaned_data = super().clean()
        for field in ("currency_from", "currency_to"):
            code = (cleaned_data.get(field) or "").upper()
            if self.currency_map and code not in self.currency_map:
                self.add_error(field, self.error_messages["invalid_choice"])
                continue
            if code:
                cleaned_data[field] = self._get_currency(code)
        return cleaned_data