from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from crispy_forms.bootstrap import FormActions
from .models import Account


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["account_name", "account_type", "currency"]

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop("show_actions", True)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.fields["currency"].required = False

        layout_fields = [
            Row(
                Column("account_name", css_class="col-md-4"),
                Column("account_type", css_class="col-md-4"),
                Column("currency", css_class="col-md-4"),
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
