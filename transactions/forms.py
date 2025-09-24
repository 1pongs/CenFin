from django import forms
from django.conf import settings
from django.db.models import Q
from decimal import Decimal
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button, HTML
from crispy_forms.bootstrap import FormActions
from .constants import TXN_TYPE_CHOICES, CATEGORY_SCOPE_BY_TX

from .models import Transaction, TransactionTemplate, CategoryTag
from accounts.models import Account
from entities.models import Entity
from entities.utils import ensure_fixed_entities
from accounts.utils import ensure_outside_account
import logging

logger = logging.getLogger(__name__)

# TransactionTemplate


# ---------------- Transaction Form ----------------
class TransactionForm(forms.ModelForm):
    _must_fill = [
        "date",
        "description",
        "transaction_type",
        "amount",
        "account_source",
        "account_destination",
        "entity_source",
        "entity_destination",
    ]
    # Replace free-text Tagify input with a dropdown of existing CategoryTag
    category = forms.ModelChoiceField(
        label="Category", required=False, queryset=CategoryTag.objects.none()
    )
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
            "template",
            "date",
            "description",
            "transaction_type",
            "amount",
            "account_source",
            "account_destination",
            "entity_source",
            "entity_destination",
            "remarks",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
            "amount": forms.TextInput(attrs={"inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        # Allow callers to request amount fields be disabled (useful for
        # update flows where amounts must remain immutable). Pop before
        # calling super so kwargs don't leak into parent.
        self._disable_amount = kwargs.pop("disable_amount", False)
        # Allow callers (like the correction view) to hide Save/Cancel
        # actions and take over with a custom submit button.
        self._show_actions = kwargs.pop("show_actions", True)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.user = user

        # If the form is bound with a transaction_type value that is normally
        # hidden in the generic form (e.g., 'cc_payment'), proactively include
        # that value in the field choices so Django's ChoiceField validation
        # accepts it. We'll still re-hide other disallowed types later and lock
        # the field to the bound value when appropriate.
        try:
            if self.is_bound and "transaction_type" in self.fields:
                posted = self.data.get("transaction_type")
                if posted:
                    # Make sure an equivalent choice exists; accept either
                    # underscore or space separated variants.
                    variants = {str(posted), str(posted).replace("_", " ")}
                    exists = any(c[0] in variants for c in self.fields["transaction_type"].choices)
                    if not exists:
                        from .constants import label_for_tx
                        # Prefer the posted raw value as the stored choice value
                        self.fields["transaction_type"].choices = list(self.fields["transaction_type"].choices) + [
                            (posted, label_for_tx(posted))
                        ]
        except Exception:
            # Best-effort safeguard; don't break form init on choice tweaks
            pass

        # Normalize legacy underscore transaction_type values on edit so they
        # match the model field choices (which use space-separated values).
        try:
            if self.instance and getattr(self.instance, "pk", None):
                t = getattr(self.instance, "transaction_type", None)
                if t and "_" in str(t):
                    spaced = str(t).replace("_", " ")
                    # Only apply when the spaced value is a valid choice
                    valid_vals = {v for v, _ in Transaction.TRANSACTION_TYPE_CHOICES}
                    if spaced in valid_vals:
                        self.instance.transaction_type = spaced
        except Exception:
            pass

        # mark amount field for live comma formatting
        css = self.fields["amount"].widget.attrs.get("class", "")
        self.fields["amount"].widget.attrs["class"] = f"{css} amount-input".strip()
        css = self.fields["destination_amount"].widget.attrs.get("class", "")
        self.fields["destination_amount"].widget.attrs[
            "class"
        ] = f"{css} amount-input".strip()
        # category select will be populated with user-specific tags
        self.fields["category"].widget.attrs["class"] = "form-select"

        # Ensure category is editable by default (some code paths may disable
        # fields based on entity/account mappings; keep category writable).
        self.fields["category"].disabled = False

        if self.instance.pk:
            # For now pick the first attached category as the selected one
            first_cat = self.instance.categories.first()
            if first_cat:
                self.initial["category"] = first_cat.pk
                # Expose the selected category id and label to the client
                # so client-side scripts can restore the selection when they
                # repopulate the select via AJAX.
                try:
                    self.fields["category"].widget.attrs[
                        "data-selected-id"
                    ] = str(first_cat.pk)
                    self.fields["category"].widget.attrs[
                        "data-selected-text"
                    ] = str(first_cat.name)
                except Exception:
                    pass
            # Pre-fill amounts when editing a cross-currency transfer
            from .models import Transaction as Tx

            children = Tx.all_objects.filter(parent_transfer=self.instance)
            if children.exists():
                outflow = children.filter(
                    account_source=self.instance.account_source
                ).first()
                inflow = children.filter(
                    account_destination=self.instance.account_destination
                ).first()
                if outflow:
                    self.initial["amount"] = outflow.amount
                if inflow:
                    self.initial["destination_amount"] = inflow.amount
                else:
                    # fallback to any existing destination_amount on the instance
                    self.initial["destination_amount"] = getattr(
                        self.instance, "destination_amount", None
                    )

            # Ensure the initial mapping contains a destination_amount key so
            # callers can reliably read it (tests expect the key to exist).
            self.initial.setdefault(
                "destination_amount", getattr(self.instance, "destination_amount", None)
            )

            # Only honor explicit caller request to disable amount fields.
            # But keep amounts editable for acquisition transactions, and
            # keep destination_amount editable for cross-currency transfers.
            if self._disable_amount:
                try:
                    ttype_inst = (getattr(self.instance, "transaction_type", "") or "").lower()
                except Exception:
                    ttype_inst = ""
                is_acq = ttype_inst in {"buy acquisition", "sell acquisition", "sell_acquisition"}
                # Cross-currency if transfer and source/destination accounts differ in currency
                try:
                    is_cross = (
                        ttype_inst == "transfer"
                        and getattr(self.instance, "account_source", None)
                        and getattr(self.instance, "account_destination", None)
                        and getattr(self.instance.account_source, "currency_id", None)
                        and getattr(self.instance.account_destination, "currency_id", None)
                        and self.instance.account_source.currency_id != self.instance.account_destination.currency_id
                    )
                except Exception:
                    is_cross = False

                # Disable the main amount unless it's an acquisition edit
                try:
                    self.fields["amount"].disabled = not is_acq
                except Exception:
                    pass
                # Disable destination_amount except when cross-currency transfer edit
                try:
                    self.fields["destination_amount"].disabled = not is_cross
                except Exception:
                    pass

            # If this instance is a read-only ledger row (loans/acquisitions),
            # mark all fields disabled so views that render the form for GET
            # show a fully read-only form. This mirrors UpdateView behavior
            # and keeps tests/components consistent.
            try:
                tx_type_inst = (
                    getattr(self.instance, "transaction_type", None) or ""
                ).lower()
            except Exception:
                tx_type_inst = None
            if tx_type_inst in {"loan_disbursement", "loan_repayment"}:
                # Loan flows remain fully read-only in the form
                for f in self.fields.values():
                    try:
                        f.disabled = True
                    except Exception:
                        pass
            elif tx_type_inst in {"buy acquisition", "sell acquisition", "sell_acquisition"}:
                # For acquisition-related transactions, only prevent
                # changing the transaction_type (and other truly immutable
                # fields like parent/child legs managed by the system). Keep
                # description/date/amount/remarks/category editable so users
                # can tweak acquisition details via the Edit buttons.
                for name, f in self.fields.items():
                    try:
                        if name == "transaction_type":
                            f.disabled = True
                    except Exception:
                        pass

        # If this is an edit of a capital return, set a sensible default for the
        # Category (Capital) when available, but do NOT override the
        # transaction_type. Capital returns should display as 'Sell Acquisition'
        # now that we map them explicitly at the model level.
        try:
            if self.instance and getattr(self.instance, "pk", None) and not self.is_bound:
                desc = (getattr(self.instance, "description", "") or "").lower()
                ttype_inst = (getattr(self.instance, "transaction_type", "") or "").lower()
                is_capital_return = (
                    "capital return" in desc
                    or ttype_inst in {"sell acquisition", "sell_acquisition"}
                )
                if is_capital_return:
                    # Pick an entity to scope the Capital tag: prefer destination, then source
                    ent_id = (
                        getattr(self.instance, "entity_destination_id", None)
                        or getattr(self.instance, "entity_source_id", None)
                    )
                    if ent_id and not self.initial.get("category"):
                        try:
                            cap_tag = (
                                CategoryTag.objects.filter(
                                    user=user, entity_id=ent_id, name__iexact="Capital"
                                )
                                .order_by("name")
                                .first()
                            )
                            if cap_tag:
                                self.initial["category"] = cap_tag.pk
                                # Also expose selection for client-side restoration
                                self.fields["category"].widget.attrs["data-selected-id"] = str(cap_tag.pk)
                                self.fields["category"].widget.attrs["data-selected-text"] = str(cap_tag.name)
                        except Exception:
                            pass
        except Exception:
            # Non-fatal: ignore defaulting errors
            pass

        account_qs = entity_qs = None
        if user is not None:
            allowed_types = ["Cash", "Banks", "E-Wallet", "Credit"]
            account_qs = (
                Account.objects.filter(
                    Q(user=user) | Q(user__isnull=True),
                    is_active=True,
                    system_hidden=False,
                )
                .filter(Q(account_type__in=allowed_types) | Q(account_type="Outside"))
                .exclude(account_name__istartswith="Remittance")
            )
            entity_qs = Entity.objects.filter(
                Q(user=user) | Q(user__isnull=True), is_active=True, system_hidden=False
            )

            self.fields["account_source"].queryset = account_qs
            self.fields["account_destination"].queryset = account_qs
            self.fields["entity_source"].queryset = entity_qs
            self.fields["entity_destination"].queryset = entity_qs

            if "template" in self.fields:
                self.fields["template"].queryset = TransactionTemplate.objects.filter(
                    user=user
                )
            # Determine current transaction type early so we can pick which
            # entity side to treat as primary for category scoping and
            # autopopulation. Use a canonical mapping in constants so it's
            # easy to adjust in one place.
            from .constants import ENTITY_SIDE_BY_TX

            tx_type = (
                self.data.get("transaction_type")
                or self.initial.get("transaction_type")
                or getattr(self.instance, "transaction_type", None)
            )
            # Allow CATEGORY_SCOPE_BY_TX to override which side is primary
            tx_key = str(tx_type).replace(" ", "_").lower() if tx_type else None
            scope = CATEGORY_SCOPE_BY_TX.get(tx_key) if tx_key else None
            if scope and scope.get("side"):
                side = scope.get("side")
            else:
                # Only derive a primary side when tx_type is present. When no
                # transaction_type is selected (creation form), avoid defaulting
                # to 'destination' so the client UI/author can choose the type
                # without fields being auto-locked to `Outside`.
                side = ENTITY_SIDE_BY_TX.get(str(tx_type).lower()) if tx_type else None

            # Select appropriate entity value based on mapping
            if side == "source":
                entity_val = (
                    self.data.get("entity_source")
                    or self.initial.get("entity_source")
                    or getattr(self.instance, "entity_source_id", None)
                )
            else:
                entity_val = (
                    self.data.get("entity_destination")
                    or self.initial.get("entity_destination")
                    or getattr(self.instance, "entity_destination_id", None)
                )

            # Populate category choices only for this user and the selected
            # entity. We intentionally do not include global tags. The
            # client-side will also call the tags API when an entity/type is
            # present to dynamically refresh the select; but rendering the
            # queryset server-side when the entity is known improves initial
            # UX (no empty select when the view already knows entity).
            if entity_val:
                try:
                    ent_id = int(entity_val)
                except Exception:
                    # If an object was provided in initial, try .id
                    ent_id = getattr(entity_val, "id", None)
                if ent_id:
                    q = CategoryTag.objects.filter(user=user, entity_id=ent_id)
                    if tx_type and str(tx_type).lower() != "all":
                        # Use central CATEGORY_SCOPE_BY_TX mapping to decide which
                        # CategoryTag.transaction_type to filter by or whether a
                        # fixed_name should be selected.
                        tx_norm = str(tx_type).strip()
                        tx_key_local = tx_norm.replace(" ", "_").lower()
                        scope_local = CATEGORY_SCOPE_BY_TX.get(tx_key_local)
                        if scope_local:
                            fixed = scope_local.get("fixed_name")
                            if fixed:
                                q = q.filter(name__iexact=fixed)
                            else:
                                cat_tx = scope_local.get("category_tx") or tx_key_local
                                alt = (
                                    cat_tx.replace("_", " ")
                                    if "_" in cat_tx
                                    else cat_tx.replace(" ", "_")
                                )
                                q = q.filter(
                                    Q(transaction_type__iexact=cat_tx)
                                    | Q(transaction_type__iexact=alt)
                                    | Q(transaction_type__isnull=True)
                                    | Q(transaction_type__exact="")
                                )
                        else:
                            alt = (
                                tx_norm.replace("_", " ")
                                if "_" in tx_norm
                                else tx_norm.replace(" ", "_")
                            )
                            q = q.filter(
                                Q(transaction_type__iexact=tx_norm)
                                | Q(transaction_type__iexact=alt)
                                | Q(transaction_type__isnull=True)
                                | Q(transaction_type__exact="")
                            )
                    # Ensure any categories already attached to the instance
                    # are included in the queryset so the previously-selected
                    # tag is visible when editing even if scoping would
                    # normally filter it out.
                    try:
                        if self.instance and getattr(self.instance, "pk", None):
                            existing_ids = list(
                                self.instance.categories.values_list("pk", flat=True)
                            )
                            if existing_ids:
                                extra = CategoryTag.objects.filter(
                                    pk__in=existing_ids, user=user
                                )
                                q = (q | extra).distinct()
                    except Exception:
                        # Best-effort: if anything goes wrong, fall back to q
                        pass
                    self.fields["category"].queryset = q.order_by("name")
                else:
                    self.fields["category"].queryset = CategoryTag.objects.none()
            else:
                # When entity is not yet selected, provide the user's global
                # category tags as a fallback so the select remains usable.
                if user is not None:
                    self.fields["category"].queryset = CategoryTag.objects.filter(
                        user=user
                    ).order_by("name")
                else:
                    self.fields["category"].queryset = CategoryTag.objects.none()

                # Also ensure any categories already attached to the instance
                # are present in the queryset so the previously-selected tag is
                # visible even when entity is not supplied in the initial data.
                try:
                    if self.instance and getattr(self.instance, "pk", None):
                        existing_ids = list(self.instance.categories.values_list("pk", flat=True))
                        if existing_ids:
                            extra = CategoryTag.objects.filter(pk__in=existing_ids, user=user)
                            self.fields["category"].queryset = (
                                (self.fields["category"].queryset | extra).distinct()
                            )
                except Exception:
                    pass

        for n in self._must_fill:
            self.fields[n].required = True

        # Relax requiredness for sides that this tx_type auto-fills to Outside:
        # - income: source side auto-filled to Outside
        # - expense/premium_payment: destination side auto-filled to Outside
        try:
            tx_req = (
                self.data.get("transaction_type")
                or self.initial.get("transaction_type")
                or getattr(self.instance, "transaction_type", None)
            )
            tx_req_l = (str(tx_req) if tx_req is not None else "").lower()
            if tx_req_l == "income":
                for name in ("account_source", "entity_source"):
                    if name in self.fields:
                        self.fields[name].required = False
            if tx_req_l in {"expense", "premium_payment"}:
                for name in ("account_destination", "entity_destination"):
                    if name in self.fields:
                        self.fields[name].required = False
        except Exception:
            pass

        # If any fields are disabled (auto-locked to Outside etc.), they
        # should not be treated as required since the client may omit their
        # values in POST. Clear the required flag for disabled fields to
        # avoid "This field is required" validation errors on submit.
        for name, field in self.fields.items():
            try:
                if getattr(field, "disabled", False):
                    field.required = False
            except Exception:
                # Best-effort; do not blow up form construction on odd fields
                pass

        # If the form is bound (POST) and the browser omitted some fields
        # because they were disabled client-side, we should not require them
        # server-side. Detect missing names in self.data and, when the
        # instance already has a value for that field, mark the field as
        # not required and ensure the initial value is set so save() can
        # fall back to the instance value.
        try:
            if self.is_bound and getattr(self, "instance", None) and getattr(
                self.instance, "pk", None
            ):
                for name, field in self.fields.items():
                    # Skip non-field form data and files
                    # If the POST omitted the field entirely, treat as missing
                    if name in self.data:
                        # If present but empty string (common when client
                        # scripts clear selects), treat as missing when the
                        # instance already has a value and the field was
                        # disabled on the client.
                        raw_val = self.data.get(name)
                        if raw_val not in (None, ""):
                            continue
                    # If the instance has an attribute for this field, use it
                    val = None
                    try:
                        # Prefer the attribute (object) when present
                        val = getattr(self.instance, name)
                    except Exception:
                        val = None
                    # Fall back to '<name>_id' for foreign keys
                    if val is None:
                        try:
                            val = getattr(self.instance, f"{name}_id", None)
                        except Exception:
                            val = None
                    if val is not None:
                        try:
                            field.required = False
                        except Exception:
                            pass
                        # Ensure the rendering/cleaning uses the instance value
                        self.initial.setdefault(name, val)
        except Exception:
            # Best-effort: don't fail form construction on odd errors
            pass

        outside_entity, _ = ensure_fixed_entities(user)
        outside_account = ensure_outside_account()
        tx_type = (
            self.data.get("transaction_type")
            or self.initial.get("transaction_type")
            or getattr(self.instance, "transaction_type", None)
        )

        # Use ENTITY_SIDE_BY_TX mapping to configure which entity/account
        # field is considered 'outside' and should be auto-filled/disabled.
        from .constants import ENTITY_SIDE_BY_TX

        # Only derive side when transaction type is explicitly present.
        side = ENTITY_SIDE_BY_TX.get(str(tx_type).lower()) if tx_type else None

        if side == "destination" and account_qs is not None and entity_qs is not None:
            # For destination-focused types (income, transfer), the destination
            # Entity/Account normally should exclude the global Outside when
            # selecting. However, some flows (notably loan repayments) submit
            # a `transaction_type` of `transfer` together with a `loan_id` to
            # indicate the transfer should be treated as a loan payment. In
            # those cases we must allow the Outside account/entity to be
            # selected, so only exclude Outside when this is not a loan flow.
            is_loan_flow = bool(self.data.get("loan_id"))
            # Also allow Outside for credit card payments where the primary side
            # is destination and the entity_destination should be Outside.
            tx_norm = (str(tx_type).lower() if tx_type else "")
            if is_loan_flow or tx_norm == "cc_payment":
                self.fields["account_destination"].queryset = account_qs
                self.fields["entity_destination"].queryset = entity_qs
            else:
                self.fields["account_destination"].queryset = account_qs.exclude(
                    account_name="Outside"
                )
                self.fields["entity_destination"].queryset = entity_qs.exclude(
                    entity_name="Outside"
                )

        # Auto-lock the opposite side to Outside where appropriate
        if side == "destination" and outside_account and outside_entity:
            # The source should be set to Outside. Only auto-lock when the
            # client did not explicitly provide an account/entity value via
            # POST or initial data. When the user provided an explicit
            # account_source, prefer that instead of overriding with Outside.
            provided_src = (
                self.data.get("account_source")
                or self.initial.get("account_source")
                or getattr(self.instance, "account_source_id", None)
            )
            provided_ent = (
                self.data.get("entity_source")
                or self.initial.get("entity_source")
                or getattr(self.instance, "entity_source_id", None)
            )
            if not provided_src and not provided_ent:
                self.fields["account_source"].initial = outside_account
                self.fields["entity_source"].initial = outside_entity
                self.fields["account_source"].disabled = True
                self.fields["entity_source"].disabled = True
        elif side == "source" and outside_account and outside_entity:
            # The destination should be set to Outside. Only auto-lock when
            # the client did not provide a destination account/entity.
            provided_dst = (
                self.data.get("account_destination")
                or self.initial.get("account_destination")
                or getattr(self.instance, "account_destination_id", None)
            )
            provided_ent_dst = (
                self.data.get("entity_destination")
                or self.initial.get("entity_destination")
                or getattr(self.instance, "entity_destination_id", None)
            )
            if not provided_dst and not provided_ent_dst:
                self.fields["account_destination"].initial = outside_account
                self.fields["entity_destination"].initial = outside_entity
                self.fields["account_destination"].disabled = True
                self.fields["entity_destination"].disabled = True

        # Remove asset/flow-specific types in generic form, but if the form is bound
        # with one of those hidden types (e.g., 'cc_payment'), keep the posted value
        # in choices so validation succeeds and lock the field to that value.
        if "transaction_type" in self.fields:
            disallowed = {
                "buy acquisition",
                "sell acquisition",
                "buy property",
                "sell property",
            }
            hidden = set()
            if type(self) is TransactionForm:
                hidden = {
                    "premium_payment",
                    "loan_disbursement",
                    "loan_repayment",
                    "cc_purchase",
                    "cc_payment",
                }

            def key_of(val):
                if val is None:
                    return None
                return str(val).replace(" ", "_").lower()

            posted_raw = None
            try:
                posted_raw = self.data.get("transaction_type") if self.is_bound else None
            except Exception:
                posted_raw = None

            exclude_keys = {key_of(x) for x in (disallowed | hidden)}

            current_type = tx_type or getattr(self.instance, "transaction_type", None)
            cur_key = key_of(current_type)

            # Special-case legacy capital return display normalization
            try:
                cur_norm_display = None
                if current_type:
                    # Prefer a human-readable display for the single-choice lock
                    cur_norm_display = str(current_type).replace("_", " ")
                if (
                    (str(cur_norm_display or "").lower() == "transfer")
                    and self.instance
                    and getattr(self.instance, "account_source", None)
                    and getattr(self.instance.account_source, "account_name", None) == "Outside"
                    and getattr(self.instance, "entity_source_id", None)
                    and getattr(self.instance, "entity_destination_id", None)
                    and self.instance.entity_source_id == self.instance.entity_destination_id
                ):
                    desc_l = (getattr(self.instance, "description", "") or "").lower()
                    if "capital return" in desc_l:
                        current_type = "sell acquisition"
                        cur_key = key_of(current_type)
                        cur_norm_display = "sell acquisition"
                        self.initial["transaction_type"] = cur_norm_display
            except Exception:
                pass

            from .constants import label_for_tx

            if cur_key in exclude_keys:
                # Lock to the current/posted type; ensure the exact posted value is accepted
                choice_val = posted_raw or current_type
                display = label_for_tx(choice_val)
                self.fields["transaction_type"].choices = [(choice_val, display)]
                self.fields["transaction_type"].disabled = True
                self.initial["transaction_type"] = choice_val
            else:
                # Filter choices by normalized keys
                base = list(self.fields["transaction_type"].choices)
                filtered = [c for c in base if key_of(c[0]) not in exclude_keys]
                # Preserve the posted raw value in choices if bound and missing
                if posted_raw and all(c[0] != posted_raw for c in filtered):
                    filtered.append((posted_raw, label_for_tx(posted_raw)))
                self.fields["transaction_type"].choices = filtered
                if current_type:
                    self.initial["transaction_type"] = current_type

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.label_class = "fw-semibold"
        self.helper.field_class = "mb-2"
        layout_fields = [
            Row(
                Column("template", css_class="col-md-6"),
                Column("description", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("date", css_class="col-md-6"),
                Column("transaction_type", css_class="col-md-6"),
                css_class="g-3",
            ),
            # Require entity/account first, then category and amount
            Row(
                Column("entity_source", css_class="col-md-6"),
                Column("entity_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source", css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("destination_amount", css_class="col-md-6"),
                css_class="g-3 d-none",
                css_id="destination_amount_wrapper",
            ),
            HTML(
                '<div id="currency_warning" class="alert alert-info d-none">The selected accounts use different currencies. Please enter both source and destination amounts.</div>'
            ),
            Row(
                Column("category", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("amount", css_class="col-md-6"),
                css_class="g-3",
            ),
            "remarks",
        ]
        if self._show_actions:
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

    def clean_transaction_type(self):
        value = self.cleaned_data.get("transaction_type")
        disallowed = {"sell acquisition", "buy property", "sell property"}
        # Allow 'buy acquisition' when the destination account is Outside and either
        # entities match or the selected type is Transfer (we will auto-convert later).
        if value == "buy acquisition":
            try:
                acc_dest_id = self.data.get("account_destination") or self.initial.get(
                    "account_destination"
                )
                ent_src_id = self.data.get("entity_source") or self.initial.get(
                    "entity_source"
                )
                ent_dst_id = self.data.get("entity_destination") or self.initial.get(
                    "entity_destination"
                )
                from accounts.models import Account

                acc = (
                    Account.objects.filter(pk=acc_dest_id).first()
                    if acc_dest_id
                    else None
                )
                dest_is_outside = bool(
                    acc
                    and (acc.account_type == "Outside" or acc.account_name == "Outside")
                )
                same_entity = (
                    ent_src_id and ent_dst_id and str(ent_src_id) == str(ent_dst_id)
                )
                # Permit this value when rule is satisfied
                if dest_is_outside and (
                    same_entity
                    or (self.data.get("transaction_type") or "").lower() == "transfer"
                ):
                    return value
            except Exception:
                pass
            # Otherwise, deny creating buy acquisition directly from this form
            raise forms.ValidationError(
                "Buy Acquisition transactions must be created from the Acquisition page unless destination is Outside with same entity/transfer."
            )
        if value in disallowed:
            if (
                self.instance
                and self.instance.pk
                and self.instance.transaction_type == value
            ):
                return value
            raise forms.ValidationError(
                "This transaction type must be created from its dedicated page."
            )
        return value

    def clean(self):
        cleaned = super().clean()
        amt = cleaned.get("amount") or Decimal("0")
        outside_entity, _ = ensure_fixed_entities(self.user)
        outside_account = ensure_outside_account()
        tx_type = cleaned.get("transaction_type")

        # Auto-fill Outside sides for specific types
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
        is_new = self.instance.pk is None

        # Pocket-aware guard for same-account transfers
        same_account_transfer = (
            (tx_type or "").lower() == "transfer"
            and acc is not None
            and dest is not None
            and getattr(acc, "id", None) == getattr(dest, "id", None)
        )
        pocket_can_cover = False
        if same_account_transfer and ent and getattr(ent, "entity_name", None) != "Outside":
            try:
                from cenfin_proj.utils import get_account_entity_balance
                pocket_bal = get_account_entity_balance(acc.id, ent.id, user=self.user)
                pocket_can_cover = bool(Decimal(str(pocket_bal or 0)) >= Decimal(str(amt or 0)))
            except Exception:
                pocket_can_cover = False

        # Account-level insufficient funds (skip for CC payment and allow when pocket covers).
        # Also skip this guard for transfers originating from an 'outside' entity
        # so cross-currency funding flows can be initiated without pre-funding.
        if acc and acc.account_name != "Outside":
            if hasattr(acc, "credit_card"):
                bal = abs(acc.get_current_balance())
                if bal + amt > acc.credit_card.credit_limit:
                    self.add_error("account_source", "Credit limit exceeded.")
            else:
                skip_for_outside_entity_transfer = (
                    (tx_type or "").lower() == "transfer"
                    and ent is not None
                    and getattr(ent, "entity_type", "").lower() == "outside"
                )
                if (
                    is_new
                    and tx_type != "cc_payment"
                    and not (same_account_transfer and pocket_can_cover)
                    and not skip_for_outside_entity_transfer
                ):
                    try:
                        bal = acc.get_current_balance() or Decimal("0")
                        if bal.quantize(Decimal("0.01")) < (amt or Decimal("0")).quantize(Decimal("0.01")):
                            self.add_error("account_source", f"Insufficient funds in {acc}.")
                    except Exception:
                        if acc.get_current_balance() < amt:
                            self.add_error("account_source", f"Insufficient funds in {acc}.")

        # Entity-level insufficient funds. Skip for transfers where the
        # source entity is of type 'outside' to allow funding into the
        # destination without pre-existing source entity liquidity.
        if is_new and ent and ent.entity_name != "Outside":
            if not getattr(ent, "is_account_entity", False):
                try:
                    from cenfin_proj.utils import get_account_entity_balance
                    pair_bal = Decimal("0")
                    if acc:
                        pair_bal = get_account_entity_balance(acc.id, ent.id)
                    ent_liquid = ent.current_balance() or Decimal("0")
                    skip_for_outside_entity_transfer = (
                        (tx_type or "").lower() == "transfer"
                        and getattr(ent, "entity_type", "").lower() == "outside"
                    )
                    if not skip_for_outside_entity_transfer and not (pair_bal >= amt or ent_liquid >= amt):
                        if same_account_transfer:
                            self.add_error("entity_source", f"Insufficient funds in {ent}.")
                        else:
                            try:
                                bal = acc.get_current_balance() if acc else Decimal("0")
                                if not acc or bal.quantize(Decimal("0.01")) < (amt or Decimal("0")).quantize(Decimal("0.01")):
                                    self.add_error("entity_source", f"Insufficient funds in {ent}.")
                            except Exception:
                                if not acc or acc.get_current_balance() < amt:
                                    self.add_error("entity_source", f"Insufficient funds in {ent}.")
                except Exception:
                    skip_for_outside_entity_transfer = (
                        (tx_type or "").lower() == "transfer"
                        and getattr(ent, "entity_type", "").lower() == "outside"
                    )
                    if not skip_for_outside_entity_transfer:
                        try:
                            ent_bal = ent.current_balance() or Decimal("0")
                            acc_bal = acc.get_current_balance() if acc else Decimal("0")
                            if ent_bal.quantize(Decimal("0.01")) < (amt or Decimal("0")).quantize(Decimal("0.01")) and (
                                not acc or acc_bal.quantize(Decimal("0.01")) < (amt or Decimal("0")).quantize(Decimal("0.01"))
                            ):
                                self.add_error("entity_source", f"Insufficient funds in {ent}.")
                        except Exception:
                            if ent.current_balance() < amt and (not acc or acc.get_current_balance() < amt):
                                self.add_error("entity_source", f"Insufficient funds in {ent}.")

        # CC payment guard
        if tx_type == "cc_payment":
            dest_acc = cleaned.get("account_destination")
            if dest_acc and hasattr(dest_acc, "credit_card"):
                bal = abs(dest_acc.get_current_balance())
                if amt > bal:
                    self.add_error("amount", "Payment amount cannot exceed current balance")

        # Currency consistency for non-transfers
        if tx_type != "transfer" and acc and dest:
            c1 = getattr(acc, "currency_id", None)
            c2 = getattr(dest, "currency_id", None)
            if c1 and c2 and c1 != c2:
                self.add_error("account_destination", "Source and destination accounts must share the same currency.")

        # Auto-convert transfer to acquisition types when Outside is involved
        try:
            acc_dest = cleaned.get("account_destination")
            acc_src = cleaned.get("account_source")
            ent_src = cleaned.get("entity_source")
            ent_dst = cleaned.get("entity_destination")
            dest_is_outside = bool(
                acc_dest and (acc_dest.account_type == "Outside" or acc_dest.account_name == "Outside")
            )
            src_is_outside = bool(
                acc_src and (acc_src.account_type == "Outside" or acc_src.account_name == "Outside")
            )
            same_entity = bool(ent_src and ent_dst and ent_src.id == ent_dst.id)
            if dest_is_outside and (same_entity or (tx_type or "").lower() == "transfer"):
                cleaned["transaction_type"] = "buy acquisition"
            elif src_is_outside and (same_entity or (tx_type or "").lower() == "transfer"):
                cleaned["transaction_type"] = "sell acquisition"
        except Exception:
            pass

        return cleaned

    def save_categories(self, transaction):
        # New behavior: category is selected from existing CategoryTag entries
        cat = self.cleaned_data.get("category")
        if cat:
            transaction.categories.set([cat])
            return

        # If the category wasn't validated (e.g. filtered out from the
        # queryset due to scoping) try to fall back to the raw POSTed value
        # so user selections aren't lost. Only accept tags owned by the user.
        raw = None
        try:
            raw = self.data.get("category")
        except Exception:
            raw = None

        if raw:
            try:
                cid = int(raw)
                tag = CategoryTag.objects.filter(pk=cid, user=self.user).first()
                if tag:
                    transaction.categories.set([tag])
                    return
            except Exception:
                pass

        # Legacy support: accept a free-text 'category_names' field and
        # create/fetch a CategoryTag for the primary entity scope.
        names_raw = None
        try:
            names_raw = self.data.get("category_names", "")
        except Exception:
            names_raw = ""
        name = (names_raw or "").strip()
        if name and getattr(self, "user", None):
            # Determine primary entity side like in __init__
            tx_type = (
                self.data.get("transaction_type")
                or self.initial.get("transaction_type")
                or getattr(self.instance, "transaction_type", None)
            )
            from .constants import CATEGORY_SCOPE_BY_TX
            ent_id = None
            if tx_type:
                tx_key = str(tx_type).replace(" ", "_").lower()
                scope = CATEGORY_SCOPE_BY_TX.get(tx_key) or {}
                side = scope.get("side")
                if not side:
                    from .constants import ENTITY_SIDE_BY_TX
                    side = ENTITY_SIDE_BY_TX.get(str(tx_type).lower(), "destination")
                try:
                    if side == "source":
                        ent_id = (
                            getattr(transaction, "entity_source_id", None)
                            or self.data.get("entity_source")
                            or self.initial.get("entity_source")
                        )
                    else:
                        ent_id = (
                            getattr(transaction, "entity_destination_id", None)
                            or self.data.get("entity_destination")
                            or self.initial.get("entity_destination")
                        )
                except Exception:
                    ent_id = None
            try:
                from .models import CategoryTag as CT
                tag = CT.objects.filter(user=self.user, name__iexact=name, entity_id=ent_id).first()
                if not tag:
                    tag = CT.objects.create(user=self.user, name=name, entity_id=ent_id, transaction_type=self.cleaned_data.get("transaction_type"))
                transaction.categories.set([tag])
                return
            except Exception:
                pass

        transaction.categories.clear()

    def save(self, commit=True):
        transaction = super().save(commit=False)
        # destination_amount isn't part of Meta.fields, handle manually.
        # If the form disabled amount fields (update flows), preserve the
        # instance values instead of overwriting with missing/None.
        if (
            self.instance
            and self.instance.pk
            and self.fields.get("amount")
            and getattr(self.fields["amount"], "disabled", False)
        ):
            transaction.amount = getattr(self.instance, "amount", transaction.amount)
        # Otherwise, ModelForm already set transaction.amount from cleaned_data

        if (
            self.instance
            and self.instance.pk
            and self.fields.get("destination_amount")
            and getattr(self.fields["destination_amount"], "disabled", False)
        ):
            transaction.destination_amount = getattr(
                self.instance, "destination_amount", transaction.destination_amount
            )
        else:
            transaction.destination_amount = self.cleaned_data.get("destination_amount")

        # Derive currency from the relevant account
        if transaction.transaction_type == "income" and transaction.account_destination:
            transaction.currency = transaction.account_destination.currency
        elif transaction.account_source:
            transaction.currency = transaction.account_source.currency
        elif transaction.account_destination:
            transaction.currency = transaction.account_destination.currency

        if self.user is not None:
            transaction.user = self.user

        if commit:
            transaction.save()
            # persist selected category (if any)
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
    # allow templates to include a category reference
    category = forms.ModelChoiceField(
        queryset=CategoryTag.objects.none(), required=False
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
            "transaction_type",
            "amount",
            "account_source",
            "account_destination",
            "entity_source",
            "entity_destination",
            "remarks",
            "category",
        ]
        widgets = {
            "amount": forms.TextInput(attrs={"inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        show_actions = kwargs.pop("show_actions", True)
        super().__init__(*args, **kwargs)
        self.user = user

        css = self.fields["amount"].widget.attrs.get("class", "")
        self.fields["amount"].widget.attrs["class"] = f"{css} amount-input".strip()

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
            self.fields["account_source"].queryset = account_qs
            self.fields["account_destination"].queryset = account_qs
            self.fields["entity_source"].queryset = entity_qs
            self.fields["entity_destination"].queryset = entity_qs
            # Templates can reference categories, but only those owned by the
            # user. We do not include global tags; authors must pick an entity
            # scoped tag. The client will help populate when appropriate.
            self.fields["category"].queryset = CategoryTag.objects.filter(
                user=user
            ).order_by("name")

        # Apply the same primary-entity mapping as TransactionForm so templates
        # can be authored with a consistent notion of which entity is primary.
        from .constants import ENTITY_SIDE_BY_TX

        side = (
            ENTITY_SIDE_BY_TX.get(str(tx_type).lower(), "destination")
            if tx_type
            else None
        )

        # Only exclude Outside from destination when a concrete tx_type is
        # selected and that type's primary side is destination (e.g. income).
        # When no type is chosen yet, keep Outside available so that selecting
        # Expense can auto-fill destination as Outside via client-side logic.
        if tx_type and side == "destination" and account_qs is not None and entity_qs is not None:
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
            # Ask for entities/accounts before amount so templates guide authors
            Row(
                Column("entity_source", css_class="col-md-6"),
                Column("entity_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("account_source", css_class="col-md-6"),
                Column("account_destination", css_class="col-md-6"),
                css_class="g-3",
            ),
            Row(
                Column("amount", css_class="col-md-6"),
                css_class="g-3",
            ),
            "remarks",
        ]

        if show_actions:
            layout_fields.append(
                FormActions(
                    Submit("save", "Save", css_class="btn btn-primary"),
                    Button(
                        "cancel",
                        "Cancel",
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
