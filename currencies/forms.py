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

    # Keep plain CharFields so the <select> values remain simple currency codes
    # which are rebuilt dynamically by JavaScript.  The ``clean_`` methods
    # convert the posted code back to a :class:`Currency` instance so that the
    # model always receives proper FK objects.
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
        if source_raw == "FRANKFURTER":
            currency_map = services.get_frankfurter_currencies()
        elif source_raw == "REM_A":
            currency_map = services.get_rem_a_currencies()
        else:  # USER
            qs = Currency.objects.filter(is_active=True)
            currency_map = {c.code: c.name for c in qs}
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
        """Return an active :class:`Currency` matching ``code``.

        If the currency does not yet exist but the code is part of
        ``self.currency_map`` we create it on the fly so that valid ISO
        codes coming from the external services can be saved without
        requiring manual seed data.
        """
        name = self.currency_map.get(code)
        if not name:
            raise forms.ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
            )

        currency, _ = Currency.objects.get_or_create(code=code, defaults={"name": name})
        if not currency.is_active:
            raise forms.ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
            )
        return currency
            
    def _clean_currency(self, field: str) -> Currency:
        """Helper for clean_currency_from/to."""
        code = (self.cleaned_data.get(field) or "").upper()
        if self.currency_map and code not in self.currency_map:
            raise forms.ValidationError(self.error_messages["invalid_choice"], code="invalid_choice")
        if code:
            return self._get_currency(code)
        return None

    def clean_currency_from(self):
        return self._clean_currency("currency_from")

    def clean_currency_to(self):
        return self._clean_currency("currency_to")