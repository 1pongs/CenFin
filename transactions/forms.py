from django import forms
from django.db.models import Q
from decimal import Decimal
from crispy_forms.helper    import FormHelper
from crispy_forms.layout    import Layout, Row, Column, Submit, Button, Field, HTML
from crispy_forms.bootstrap import FormActions
from .constants import TXN_TYPE_CHOICES

from .models import Transaction, TransactionTemplate, CategoryTag
from accounts.models import Account
from entities.models import Entity
from entities.utils import ensure_fixed_entities
from accounts.utils import ensure_outside_account

#TransactionTemplate

# ---------------- Transaction Form ----------------
class TransactionForm(forms.ModelForm):
    _must_fill = [
        "date", "description",
        "transaction_type", "amount",
        "account_source", "account_destination",
        "entity_source", "entity_destination",
    ]
    category_names = forms.CharField(label="Category", required=False)
    destination_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        label="Account Destination Amount",
    )
    
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
            "amount":  forms.TextInput(attrs={"inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.user = user



         # mark amount field for live comma formatting
        css = self.fields['amount'].widget.attrs.get('class', '')
        self.fields['amount'].widget.attrs['class'] = f"{css} amount-input".strip()
        css = self.fields['destination_amount'].widget.attrs.get('class', '')
        self.fields['destination_amount'].widget.attrs['class'] = f"{css} amount-input".strip()
        self.fields['category_names'].widget.attrs['class'] = 'tag-input form-control'

        if self.instance.pk:
            self.initial['category_names'] = ','.join(
                t.name for t in self.instance.categories.all()
            )
            # Pre-fill amounts when editing a cross-currency transfer
            from .models import Transaction as Tx
            children = Tx.all_objects.filter(parent_transfer=self.instance)
            if children.exists():
                outflow = children.filter(account_source=self.instance.account_source).first()
                inflow = children.filter(account_destination=self.instance.account_destination).first()
                if outflow:
                    self.initial['amount'] = outflow.amount
                if inflow:
                    self.initial['destination_amount'] = inflow.amount

        account_qs = entity_qs = None
        if user is not None:
            allowed_types = ["Cash", "Banks", "E-Wallet", "Credit"]
            account_qs = Account.objects.filter(
                Q(user=user) | Q(user__isnull=True),
                is_active=True,
                system_hidden=False,
            ).filter(Q(account_type__in=allowed_types) | Q(account_type="Outside"))
            entity_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True, system_hidden=False
            )

            self.fields['account_source'].queryset = account_qs
            self.fields['account_destination'].queryset = account_qs
            self.fields['entity_source'].queryset = entity_qs
            self.fields['entity_destination'].queryset = entity_qs

            if 'template' in self.fields:
                self.fields['template'].queryset = (
                    TransactionTemplate.objects.filter(user=user)
                )

        for n in self._must_fill:
            self.fields[n].required = True

        outside_entity, _ = ensure_fixed_entities(user)
        outside_account = ensure_outside_account()
        tx_type = (self.data.get("transaction_type")
                   or self.initial.get("transaction_type")
                   or getattr(self.instance, "transaction_type", None))

        if tx_type == "income" and account_qs is not None and entity_qs is not None:
            self.fields["account_destination"].queryset = account_qs.exclude(account_name="Outside")
            self.fields["entity_destination"].queryset = entity_qs.exclude(entity_name="Outside")

        if tx_type == "income" and outside_account and outside_entity:
            self.fields["account_source"].initial = outside_account
            self.fields["entity_source"].initial  = outside_entity
            self.fields["account_source"].disabled = True
            self.fields["entity_source"].disabled  = True
        if tx_type == "expense" and outside_account and outside_entity:
            self.fields["account_destination"].initial = outside_account
            self.fields["entity_destination"].initial  = outside_entity
            self.fields["account_destination"].disabled = True
            self.fields["entity_destination"].disabled  = True
        if tx_type == "premium_payment" and outside_account and outside_entity:
            self.fields["account_destination"].initial = outside_account
            self.fields["entity_destination"].initial  = outside_entity
            self.fields["account_destination"].disabled = True
            self.fields["entity_destination"].disabled  = True

         # Remove asset-related transaction types when using this form
        if 'transaction_type' in self.fields:
            disallowed = {
                'buy acquisition', 'sell acquisition',
                'buy property', 'sell property'
            }
            hidden = set()
            if type(self) is TransactionForm:
                hidden = {
                    'premium_payment', 'loan_disbursement',
                    'cc_purchase'
                }
            current_type = getattr(self.instance, 'transaction_type', None)

            if current_type in disallowed | hidden:
                self.fields['transaction_type'].choices = [
                    (current_type, current_type.replace('_', ' ').title())
                ]
                self.fields['transaction_type'].disabled = True
            else:
                self.fields['transaction_type'].choices = [
                    c for c in self.fields['transaction_type'].choices
                    if c[0] not in disallowed | hidden
                ]

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
                Column("category_names", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("amount",   css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("destination_amount", css_class="col-md-6"),
                css_class="g-3 d-none",
                css_id="destination_amount_wrapper",
            ),
            HTML('<div id="currency_warning" class="alert alert-info d-none">The selected accounts use different currencies. Please enter both source and destination amounts.</div>'),
            Row(
                Column("entity_source",       css_class="col-md-6"),
                Column("entity_destination",  css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source",      css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
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

    def clean_transaction_type(self):
        value = self.cleaned_data.get('transaction_type')
        disallowed = {'buy acquisition', 'sell acquisition', 'buy property', 'sell property'}
        if value in disallowed:
            if self.instance and self.instance.pk and self.instance.transaction_type == value:
                return value
        if value in {'buy acquisition', 'sell acquisition', 'buy property', 'sell property'}:
            raise forms.ValidationError(
                "Buy/Sell Acquisition transactions must be created from the Acquisition page."
            )
        return value
    
    def clean(self):
        cleaned = super().clean()
        amt = cleaned.get("amount") or Decimal("0")
        outside_entity, _ = ensure_fixed_entities(self.user)
        outside_account = ensure_outside_account()
        tx_type = cleaned.get("transaction_type")

        if tx_type == "income" and outside_account and outside_entity:
            cleaned["account_source"] = outside_account
            cleaned["entity_source"] = outside_entity
        if tx_type == "expense" and outside_account and outside_entity:
            cleaned["account_destination"] = outside_account
            cleaned["entity_destination"] = outside_entity
        if tx_type == "premium_payment" and outside_account and outside_entity:
            cleaned["account_destination"] = outside_account
            cleaned["entity_destination"] = outside_entity
        acc = cleaned.get("account_source")
        dest = cleaned.get("account_destination")
        ent = cleaned.get("entity_source")

        if acc and acc.account_name != "Outside":
            if hasattr(acc, "credit_card"):
                bal = abs(acc.get_current_balance())
                if bal + amt > acc.credit_card.credit_limit:
                    self.add_error(
                        "account_source",
                        "Credit limit exceeded.",
                    )
            elif acc.get_current_balance() < amt:
                self.add_error("account_source", f"Insufficient funds in {acc}.")

        if ent and ent.entity_name != "Outside":
            if not getattr(ent, "is_account_entity", False) and ent.current_balance() < amt:
                self.add_error("entity_source", f"Insufficient funds in {ent}.")

        if tx_type == "cc_payment":
            dest_acc = cleaned.get("account_destination")
            if dest_acc and hasattr(dest_acc, "credit_card"):
                bal = abs(dest_acc.get_current_balance())
                if amt > bal:
                    self.add_error("amount", "Payment amount cannot exceed current balance")
    


        # For single-leg transactions (non-transfer), ensure both accounts use the
        # same currency
        if tx_type != "transfer" and acc and dest:
            c1 = getattr(acc, "currency_id", None)
            c2 = getattr(dest, "currency_id", None)
            if c1 and c2 and c1 != c2:
                self.add_error(
                    "account_destination",
                    "Source and destination accounts must share the same currency.",
                )

        return cleaned

    def save_categories(self, transaction):
        names = [
            n.strip()
            for n in (self.cleaned_data.get("category_names") or "").split(",")
            if n.strip()
        ]
        tags = []
        tx_type = transaction.transaction_type
        for name in names:
            tag, _ = CategoryTag.objects.get_or_create(
                user=self.user, transaction_type=tx_type, name=name
            )
            tags.append(tag)
        transaction.categories.set(tags)

    def save(self, commit=True):
        transaction = super().save(commit=False)
        # destination_amount isn't part of Meta.fields, handle manually
        transaction.destination_amount = self.cleaned_data.get("destination_amount")

        # Derive currency from the relevant account
        if transaction.transaction_type == "income" and transaction.account_destination:
            transaction.currency = transaction.account_destination.currency
        elif transaction.account_source:
            transaction.currency = transaction.account_source.currency
        elif transaction.account_destination:
            transaction.currency = transaction.account_destination.currency

        if commit:
            transaction.save()
            self.save_categories(transaction)
        return transaction

# ---------------- Template Form ----------------
class TemplateForm(forms.ModelForm):

    description = forms.CharField(max_length=255, required=False)
    transaction_type = forms.ChoiceField(
        choices=TXN_TYPE_CHOICES,
        required=False,
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
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
            "description",
            "transaction_type", "amount",
            "account_source", "account_destination",
            "entity_source", "entity_destination",
            "remarks",
        ]
        widgets = {
            "amount": forms.TextInput(attrs={"inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        show_actions = kwargs.pop('show_actions', True)
        super().__init__(*args, **kwargs)
        self.user = user

        css = self.fields['amount'].widget.attrs.get('class', '')
        self.fields['amount'].widget.attrs['class'] = f"{css} amount-input".strip()

        outside_entity, _ = ensure_fixed_entities(self.user)
        outside_account = ensure_outside_account()
        tx_type = (
            self.data.get("transaction_type")
            or self.initial.get("transaction_type")
            or getattr(self.instance, "transaction_type", None)
        )

        account_qs = entity_qs = None
        if user is not None:
            allowed_types = ["Cash", "Banks", "E-Wallet", "Credit"]
            account_qs = Account.objects.filter(
                Q(user=user) | Q(user__isnull=True),
                is_active=True,
            ).filter(Q(account_type__in=allowed_types) | Q(account_type="Outside"))
            entity_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True
            )
            self.fields['account_source'].queryset = account_qs
            self.fields['account_destination'].queryset = account_qs
            self.fields['entity_source'].queryset = entity_qs
            self.fields['entity_destination'].queryset = entity_qs

        if tx_type == "income" and account_qs is not None and entity_qs is not None:
            self.fields["account_destination"].queryset = account_qs.exclude(account_name="Outside")
            self.fields["entity_destination"].queryset = entity_qs.exclude(entity_name="Outside")

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

        if tx_type == "income":
            self.fields["account_source"].initial = outside_account
            self.fields["entity_source"].initial = outside_entity
            self.fields["account_source"].disabled = True
            self.fields["entity_source"].disabled = True
        elif tx_type == "expense":
            self.fields["account_destination"].initial = outside_account
            self.fields["entity_destination"].initial = outside_entity
            self.fields["account_destination"].disabled = True
            self.fields["entity_destination"].disabled = True
        elif tx_type == "premium_payment":
            self.fields["account_destination"].initial = outside_account
            self.fields["entity_destination"].initial = outside_entity
            self.fields["account_destination"].disabled = True
            self.fields["entity_destination"].disabled = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        
        layout_fields = [
            Row(
                Column("name", css_class="col-md-6"),
                Column("description", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
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

    def clean(self):
        cleaned = super().clean()
        tx_type = cleaned.get("transaction_type")
        outside_entity, _ = ensure_fixed_entities(self.user)
        outside_account = ensure_outside_account()
        if tx_type == "income":
            cleaned["account_source"] = outside_account
            cleaned["entity_source"] = outside_entity
        elif tx_type == "expense":
            cleaned["account_destination"] = outside_account
            cleaned["entity_destination"] = outside_entity
        elif tx_type == "premium_payment":
            cleaned["account_destination"] = outside_account
            cleaned["entity_destination"] = outside_entity
        return cleaned

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