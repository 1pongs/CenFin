from django import forms
from django.db.models import Q
from crispy_forms.helper    import FormHelper
from crispy_forms.layout    import Layout, Row, Column, Submit, Button, Field
from crispy_forms.bootstrap import FormActions
from .constants import TXN_TYPE_CHOICES

from .models import Transaction, TransactionTemplate
from accounts.models import Account
from entities.models import Entity

#TransactionTemplate

# ---------------- Transaction Form ----------------
class TransactionForm(forms.ModelForm):
    _must_fill = [
        "date", "description",
        "transaction_type", "amount",
        "account_source", "account_destination",
        "entity_source", "entity_destination",
    ]
    
    class Meta:
        model = Transaction
        fields = [
            "template", "date", "description",
            "transaction_type", "amount",
            "account_source", "account_destination",
            "entity_source", "entity_destination",
            "remarks",
        ]
        widgets = {
            "date":    forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

        

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user is not None:
            account_qs = Account.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            entity_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )

            self.fields['account_source'].queryset = account_qs
            self.fields['account_destination'].queryset = account_qs
            self.fields['entity_source'].queryset = entity_qs
            self.fields['entity_destination'].queryset = entity_qs            
            self.fields['template'].queryset = TransactionTemplate.objects.filter(user=user)

        for n in self._must_fill:
            self.fields[n].required = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method  = "post"
        self.helper.label_class  = "fw-semibold"
        self.helper.field_class  = "mb-2"
        self.helper.layout = Layout(
            Row(
                Column("template",       css_class="col-md-6"),
                Column("description",    css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("date",           css_class="col-md-6"),
                Column("transaction_type", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("amount",           css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source",      css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("entity_source",       css_class="col-md-6"),
                Column("entity_destination",  css_class="col-md-6"),
                css_class="g-3",
            ),
            "remarks",
            FormActions(
                Submit("save", "Save", css_class="btn btn-primary"),
                Button(
                    "cancel", "Cancel",
                    css_class="btn btn-outline-secondary",
                    onclick="history.back()",
            ),
            css_class="d-flex justify-content-end gap-2 mt-3",
        ),
    )

# ---------------- Template Form ----------------
class TemplateForm(forms.ModelForm):
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    description = forms.CharField(max_length=255, required=False)
    transaction_type = forms.ChoiceField(
        choices=TXN_TYPE_CHOICES,
        required=False,
    )
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    account_source = forms.ModelChoiceField(
        queryset=Account.objects.all(), required=False
    )
    account_destination = forms.ModelChoiceField(
        queryset=Account.objects.all(), required=False
    )
    entity_source = forms.ModelChoiceField(
        queryset=Entity.objects.all(), required=False
    )
    entity_destination = forms.ModelChoiceField(
        queryset=Entity.objects.all(), required=False
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
    )

    class Meta:
        model = TransactionTemplate
        fields = [
            "name",             
            "date", "description",
            "transaction_type", "amount",
            "account_source", "account_destination",
            "entity_source", "entity_destination",
            "remarks",
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        show_actions = kwargs.pop('show_actions', True)
        super().__init__(*args, **kwargs)

        if user is not None:
            account_qs = Account.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            entity_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            self.fields['account_source'].queryset = account_qs
            self.fields['account_destination'].queryset = account_qs
            self.fields['entity_source'].queryset = entity_qs
            self.fields['entity_destination'].queryset = entity_qs

        if self.instance and self.instance.autopop_map:
            for field_name, value in self.instance.autopop_map.items():
                if field_name not in self.fields:
                    continue
                field = self.fields[field_name]
                if isinstance(field, forms.ModelChoiceField):
                    obj = field.queryset.filter(pk=value).first()
                    if obj:
                        self.initial[field_name] = obj
                else:
                    self.initial[field_name] = value

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        layout_fields = [
            Row(
                Column("name", css_class="col-md-6"),
                Column("description", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("date", css_class="col-md-6"),
                Column("transaction_type", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("amount", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source", css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("entity_source", css_class="col-md-6"),
                Column("entity_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            "remarks",
        ]

        if show_actions:
            layout_fields.append(
                FormActions(
                    Submit("save", "Save", css_class="btn btn-primary"),
                    Button(
                        "cancel", "Cancel",
                        css_class="btn btn-outline-secondary ms-2",
                        onclick="history.back()",
                    ),
                )
            )

        self.helper.layout = Layout(*layout_fields)

    def save(self, commit=True):
        template = super().save(commit=False)
        defaults = {}
        for field_name in self.cleaned_data:
            if field_name == "name":
                continue
            value = self.cleaned_data.get(field_name)
            if value not in (None, "", []):
                defaults[field_name] = value.pk if hasattr(value, "pk") else value
        template.autopop_map = defaults or None

        if commit:
            template.save()
        return template