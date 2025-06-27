from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from crispy_forms.bootstrap import FormActions
from django.urls import reverse_lazy
from .models import Loan, CreditCard, Lender

class LoanForm(forms.ModelForm):
    lender_name = forms.CharField(label="Lender")

    class Meta:
        model = Loan
        fields = [
            'lender', 'lender_name', 'principal_amount', 'interest_rate',
            'received_date', 'term_months'
        ]
        widgets = {
            'received_date': forms.DateInput(attrs={'type': 'date'}),
            'lender': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop('show_actions', True)
        cancel_url = kwargs.pop('cancel_url', reverse_lazy("liabilities:list"))
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields['lender'].required = False
        self.fields['lender_name'].required = False
        self.fields['lender_name'].widget.attrs.update({'list': 'lender-list', 'autocomplete': 'off'})
        for fld in ['principal_amount', 'interest_rate']:
            attrs = self.fields[fld].widget.attrs
            css = attrs.get('class', '')
            # use TextInput so our JS formatter can insert commas
            self.fields[fld].widget = forms.TextInput(attrs=attrs)
            self.fields[fld].widget.attrs['class'] = f"{css} amount-input".strip()
            self.fields[fld].widget.attrs.setdefault('inputmode', 'decimal')

        layout_fields = [
            Row(
                Column('lender_name', css_class='col-md-6'),
                Column('principal_amount', css_class='col-md-6'),
                css_class='g-3'
            ),
            Row(
                Column('interest_rate', css_class='col-md-6'),
                Column('term_months', css_class='col-md-6'),
                css_class='g-3'
            ),
            Row(Column('received_date', css_class='col-md-6'), css_class='g-3')
        ]
        if show_actions:
            layout_fields.append(
                FormActions(
                    Submit('save', 'Save', css_class='btn btn-primary'),
                    Button('cancel', 'Cancel', type='button', css_class='btn btn-outline-secondary', onclick=f"window.location.href='{cancel_url}'"),
                    css_class='d-flex justify-content-end gap-2 mt-3'
                )
            )
        self.helper.layout = Layout(*layout_fields)

    def clean(self):
        cleaned_data = super().clean()
        lender = cleaned_data.get('lender')
        name = (cleaned_data.get('lender_name') or '').strip()
        if not lender and not name:
            self.add_error('lender_name', 'Lender is required — select one or create a new lender first.')
        if not lender and name:
            if Lender.objects.filter(name__iexact=name).exists():
                self.add_error('lender_name', 'Lender already exists.')
        return cleaned_data

class CreditCardForm(forms.ModelForm):
    issuer_name = forms.CharField(label="Issuer")

    class Meta:
        model = CreditCard
        fields = ['issuer', 'issuer_name', 'card_name', 'credit_limit', 'interest_rate', 'statement_day', 'payment_due_day']
        widgets = {
            'issuer': forms.HiddenInput(),
        }
    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop('show_actions', True)
        cancel_url = kwargs.pop('cancel_url', reverse_lazy("liabilities:list"))
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields['issuer'].required = False
        self.fields['issuer_name'].required = False
        self.fields['issuer_name'].widget.attrs.update({'list': 'issuer-list', 'autocomplete': 'off'})
        for fld in ['credit_limit', 'interest_rate']:
            attrs = self.fields[fld].widget.attrs
            css = attrs.get('class', '')
            self.fields[fld].widget = forms.TextInput(attrs=attrs)
            self.fields[fld].widget.attrs['class'] = f"{css} amount-input".strip()
            self.fields[fld].widget.attrs.setdefault('inputmode', 'decimal')
        layout_fields = [
            Row(
                Column('issuer_name', css_class='col-md-6'),
                Column('card_name', css_class='col-md-6'),
                css_class='g-3'
            ),
            Row(
                Column('credit_limit', css_class='col-md-6'),
                Column('interest_rate', css_class='col-md-6'),
                css_class='g-3'
            ),
            Row(
                Column('statement_day', css_class='col-md-6'),
                Column('payment_due_day', css_class='col-md-6'),
                css_class='g-3'
            )
        ]
        if show_actions:
            layout_fields.append(
                FormActions(
                    Submit('save', 'Save', css_class='btn btn-primary'),
                    Button('cancel', 'Cancel', type='button', css_class='btn btn-outline-secondary', onclick=f"window.location.href='{cancel_url}'"),
                    css_class='d-flex justify-content-end gap-2 mt-3'
                )
            )
        self.helper.layout = Layout(*layout_fields)

    def clean(self):
        cleaned_data = super().clean()
        issuer = cleaned_data.get('issuer')
        name = (cleaned_data.get('issuer_name') or '').strip()

        if not issuer and not name:
            self.add_error('issuer_name', 'Issuer is required — select one or create a new issuer first.')
        if not issuer and name:
            if Lender.objects.filter(name__iexact=name).exists():
                self.add_error('issuer_name', 'Issuer already exists.')
        return cleaned_data