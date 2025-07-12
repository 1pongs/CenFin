from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button, Field
from crispy_forms.bootstrap import FormActions
from django.urls import reverse_lazy
from accounts.models import Account
from entities.models import Entity
from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities
from currencies.models import Currency
from .models import Loan, CreditCard, Lender

class LoanForm(forms.ModelForm):
    lender_id = forms.ModelChoiceField(queryset=Lender.objects.all(), widget=forms.HiddenInput(), required=False)
    lender_text = forms.CharField(label="Lender / Issuer", required=False)
    account_destination = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        label="Account Destination"
    )
    account_source = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.HiddenInput(),
        required=False
    )
    entity_source = forms.ModelChoiceField(
        queryset=Entity.objects.none(),
        widget=forms.HiddenInput(),
        required=False
    )
    entity_destination = forms.ModelChoiceField(
        queryset=Entity.objects.none(),
        widget=forms.HiddenInput(),
        required=False
    )
    currency = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = Loan
        fields = [
            'lender_id', 'lender_text', 'principal_amount', 'interest_rate',
            'received_date', 'term_months', 'currency'
        ]
        widgets = {
            'received_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop('show_actions', True)
        cancel_url = kwargs.pop('cancel_url', reverse_lazy("liabilities:list"))
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields['lender_id'].required = False
        self.fields['lender_text'].required = False
        self.fields['lender_text'].widget.attrs.update({'list': 'lender-list', 'autocomplete': 'off'})
        choices = [(c.code, f"{c.code} — {c.name}") for c in Currency.objects.filter(is_active=True)]
        self.fields['currency'].choices = choices
        if self.instance.pk:
            self.fields['currency'].initial = self.instance.currency
        elif user and getattr(user, 'base_currency_id', None):
            self.fields['currency'].initial = user.base_currency.code
        elif choices:
            self.fields['currency'].initial = choices[0][0]
        if self.instance.pk and self.instance.lender_id:
            self.fields['lender_id'].initial = self.instance.lender_id
            self.fields['lender_text'].initial = self.instance.lender.name
        if user is not None:
            account_qs = Account.objects.filter(user=user)
            self.fields['account_destination'].queryset = account_qs
            outside_acc = ensure_outside_account()
            outside_ent, account_ent = ensure_fixed_entities(user)
            self.fields['account_source'].queryset = Account.objects.filter(pk=outside_acc.pk)
            self.fields['account_source'].initial = outside_acc
            self.fields['entity_source'].queryset = Entity.objects.filter(pk=outside_ent.pk)
            self.fields['entity_source'].initial = outside_ent
            self.fields['entity_destination'].queryset = Entity.objects.filter(pk=account_ent.pk)
            self.fields['entity_destination'].initial = account_ent

        if self.instance.pk and getattr(self.instance, "disbursement_tx_id", None):
            tx = self.instance.disbursement_tx
            self.fields["account_destination"].initial = tx.account_destination_id
            self.fields["account_source"].initial = tx.account_source_id
            self.fields["entity_source"].initial = tx.entity_source_id
            self.fields["entity_destination"].initial = tx.entity_destination_id

        for fld in ['principal_amount', 'interest_rate']:
            attrs = self.fields[fld].widget.attrs
            css = attrs.get('class', '')
            # use TextInput so our JS formatter can insert commas
            self.fields[fld].widget = forms.TextInput(attrs=attrs)
            self.fields[fld].widget.attrs['class'] = f"{css} amount-input".strip()
            self.fields[fld].widget.attrs.setdefault('inputmode', 'decimal')

        layout_fields = [
            Row(
                Column('lender_text', css_class='col-md-6'),
                Column('principal_amount', css_class='col-md-6'),
                css_class='g-3'
            ),
            Row(
                Column('interest_rate', css_class='col-md-4'),
                Column('term_months', css_class='col-md-4'),
                Column('currency', css_class='col-md-4'),
                css_class='g-3'
            ),
            Row(Column('account_destination', css_class='col-md-6'), css_class='g-3'),
            Field('account_source'),
            Field('entity_source'),
            Field('entity_destination'),
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
        lender = cleaned_data.get('lender_id')
        name = (cleaned_data.get('lender_text') or '').strip()
        if lender:
            self.instance.lender = lender
        else:
            if not name:
                self.add_error('lender_text', 'Lender is required — select one or create a new lender first.')
            else:
                self.instance.lender, _ = Lender.objects.get_or_create(name__iexact=name, defaults={'name': name})
        return cleaned_data
    
    def save(self, commit=True):
        loan = super().save(commit=False)
        loan._account_destination = self.cleaned_data.get('account_destination')
        loan._account_source = self.cleaned_data.get('account_source')
        loan._entity_source = self.cleaned_data.get('entity_source')
        loan._entity_destination = self.cleaned_data.get('entity_destination')
        if commit:
            loan.save()
        return loan


class CreditCardForm(forms.ModelForm):
    issuer_id = forms.ModelChoiceField(queryset=Lender.objects.all(), widget=forms.HiddenInput(), required=False)
    issuer_text = forms.CharField(label="Lender / Issuer", required=False)
    currency = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = CreditCard
        fields = ['issuer_id', 'issuer_text', 'card_name', 'credit_limit', 'interest_rate', 'currency', 'statement_day', 'payment_due_day']
    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop('show_actions', True)
        cancel_url = kwargs.pop('cancel_url', reverse_lazy("liabilities:list"))
        user = kwargs.pop('user', None)
        self.user = user
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields['issuer_id'].required = False
        self.fields['issuer_text'].required = False
        self.fields['issuer_text'].widget.attrs.update({'list': 'issuer-list', 'autocomplete': 'off'})
        choices = [(c.code, f"{c.code} — {c.name}") for c in Currency.objects.filter(is_active=True)]
        self.fields['currency'].choices = choices
        if self.instance.pk:
            self.fields['currency'].initial = self.instance.currency
        elif user and getattr(user, 'base_currency_id', None):
            self.fields['currency'].initial = user.base_currency.code
        elif choices:
            self.fields['currency'].initial = choices[0][0]
        if self.instance.pk and self.instance.issuer_id:
            self.fields['issuer_id'].initial = self.instance.issuer_id
            self.fields['issuer_text'].initial = self.instance.issuer.name
        for fld in ['credit_limit', 'interest_rate']:
            attrs = self.fields[fld].widget.attrs
            css = attrs.get('class', '')
            self.fields[fld].widget = forms.TextInput(attrs=attrs)
            self.fields[fld].widget.attrs['class'] = f"{css} amount-input".strip()
            self.fields[fld].widget.attrs.setdefault('inputmode', 'decimal')
        layout_fields = [
            Row(
                Column('issuer_text', css_class='col-md-6'),
                Column('card_name', css_class='col-md-6'),
                css_class='g-3'
            ),
            Row(
                Column('credit_limit', css_class='col-md-4'),
                Column('interest_rate', css_class='col-md-4'),
                Column('currency', css_class='col-md-4'),
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

    def clean_card_name(self):
        name = (self.cleaned_data.get('card_name') or '').strip()
        if not name:
            return name
        from accounts.models import Account
        qs = Account.objects.filter(account_name__iexact=name, user=self.user)
        if self.instance.pk and self.instance.account_id:
            qs = qs.exclude(pk=self.instance.account_id)
        if qs.filter(is_active=True).exists():
            raise forms.ValidationError('Name already in use.')
        return name
    
    def clean(self):
        cleaned_data = super().clean()
        issuer = cleaned_data.get('issuer_id')
        name = (cleaned_data.get('issuer_text') or '').strip()

        if issuer:
            self.instance.issuer = issuer
        else:
            if not name:
                self.add_error('issuer_text', 'Issuer is required — select one or create a new issuer first.')
            else:
                self.instance.issuer, _ = Lender.objects.get_or_create(name__iexact=name, defaults={'name': name})
        return cleaned_data