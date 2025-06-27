from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from crispy_forms.bootstrap import FormActions
from .models import Loan, CreditCard

class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = [
            'lender', 'principal_amount', 'interest_rate',
            'received_date', 'term_months'
        ]
        widgets = {'received_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop('show_actions', True)
        cancel_url = kwargs.pop('cancel_url', '#')
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        layout_fields = [
            Row(
                Column('lender', css_class='col-md-6'),
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

class CreditCardForm(forms.ModelForm):
    class Meta:
        model = CreditCard
        fields = ['issuer', 'card_name', 'credit_limit', 'interest_rate', 'statement_day', 'payment_due_day']

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop('show_actions', True)
        cancel_url = kwargs.pop('cancel_url', '#')
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        layout_fields = [
            Row(
                Column('issuer', css_class='col-md-6'),
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