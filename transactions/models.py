from django.db import models
import re
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from accounts.models import Account
from entities.models import Entity
from currencies.models import Currency
from django.db.models import JSONField, Max, Q
from django.core.exceptions import ValidationError
from .constants import transaction_type_TX_MAP, TXN_TYPE_CHOICES
from cenfin_proj.utils import (
    get_account_entity_balance,
    get_entity_balance as util_entity_balance,
)

# Create your models here.

class TransactionTemplate(models.Model):
    name = models.CharField(max_length=60, unique=True)
    autopop_map = models.JSONField(default=dict, blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transaction_templates", null=True)

    def __str__(self):
        return self.name
    
class CategoryTag(models.Model):
    """User-defined tag for categorizing transactions."""
    name = models.CharField(max_length=60)
    # Normalized key for case/plural-insensitive uniqueness (lowercased, basic singular)
    name_key = models.CharField(max_length=80, editable=False, db_index=True, default="")
    transaction_type = models.CharField(
        max_length=20, choices=TXN_TYPE_CHOICES, blank=True, null=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="category_tags",
    )
    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        related_name="category_tags",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Enforce uniqueness on normalized name within the user/type/entity scope
        unique_together = ("user", "transaction_type", "name_key", "entity")

    def __str__(self):
        return self.name

    @staticmethod
    def _normalize_name(value: str) -> str:
        """Normalize a tag name for uniqueness.

        - Lowercase
        - Trim spaces
        - Collapse internal whitespace to single space
        - Very light singularization: drop a single trailing 's' when length > 4
        - Remove non-alphanumeric characters except space, then remove spaces

        This intentionally keeps logic simple to cover cases like
        "Capital" vs "capital" vs "Capitals" mapping to the same key.
        """
        if not value:
            return ""
        v = " ".join((value or "").strip().lower().split())
        if len(v) > 4 and v.endswith("s") and not v.endswith("ss"):
            v = v[:-1]
        # keep alphanumerics only to avoid differences like hyphens/underscores
        v = re.sub(r"[^a-z0-9]+", "", v)
        return v

    def clean(self):
        super().clean()
        # Always compute the normalized key
        self.name_key = self._normalize_name(self.name)
        # Enforce uniqueness for both global and entity-scoped tags using the key
        exists = (
            self.__class__.objects.filter(
                user=self.user,
                transaction_type=self.transaction_type,
                name_key=self.name_key,
                entity_id=self.entity_id,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if exists:
            raise ValidationError("Category with an equivalent name already exists.")

    def save(self, *args, **kwargs):
        # Ensure name_key is set before saving
        self.name_key = self._normalize_name(self.name)
        return super().save(*args, **kwargs)
                
class TransactionQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_hidden=False)


class TransactionManager(models.Manager):
    def get_queryset(self):
        return TransactionQuerySet(self.model, using=self._db).filter(is_hidden=False)

    def with_hidden(self):
        return TransactionQuerySet(self.model, using=self._db)

class Transaction(models.Model):
    template = models.ForeignKey(
        TransactionTemplate,
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions", null=True)
    
    TRANSACTION_TYPE_CHOICES = [
        ("income", "Income"),
        ("expense", "Expense"),
        ("premium_payment", "Premium Payment"),
        ("buy acquisition", "Buy Acquisition"),
        ("sell acquisition", "Sell Acquisition"),
        ("transfer", "Transfer"),
        ("loan_disbursement", "Loan Disbursement"),
        ("loan_repayment", "Loan Repayment"),
        ("cc_purchase", "Cc Purchase"),
        ("cc_payment", "Cc Payment"),
    ]

    date = models.DateField(default=timezone.now, null=True, blank=True,)
    description = models.CharField(max_length=255, null=True, blank=True,)

    account_source = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        related_name='transaction_as_source',
        null=True,
        blank=True,
        limit_choices_to={'is_active': True},
        db_index=True,
    )
    account_destination = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        related_name='transaction_as_destination',
        null=True,
        blank=True,
        limit_choices_to={'is_active': True},
        db_index=True,
    )

    entity_source = models.ForeignKey(
        Entity, on_delete=models.SET_NULL,
        related_name='transaction_entity_source',
        null=True,
        blank=True,
        limit_choices_to={'is_active':True},
    )
    entity_destination = models.ForeignKey(
        Entity, on_delete=models.SET_NULL,
        related_name='transaction_entity_destination',
        null=True,
        blank=True,
        limit_choices_to={'is_active':True},
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, blank=True, null=True)
    transaction_type_source = models.CharField(max_length=20, editable=False, blank=True, null=True)
    transaction_type_destination = models.CharField(max_length=20, editable=False, blank=True, null=True)

    asset_type_source = models.CharField(max_length=20, editable=False, blank=True, null=True)
    asset_type_destination = models.CharField(max_length=20, editable=False, blank=True, null=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    destination_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
    )
    categories = models.ManyToManyField(CategoryTag, related_name="transactions", blank=True)
    remarks = models.TextField(blank=True, null=True)
    is_hidden = models.BooleanField(default=False)
    parent_transfer = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_transfers')

    # ledger management fields
    ledger_status = models.CharField(
        max_length=10,
        choices=[
            ("posted", "Posted"),
            ("reversed", "Reversed"),
            ("deleted", "Deleted"),
        ],
        default="posted",
        db_index=True,
    )
    posted_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    seq_account = models.IntegerField(null=True, blank=True, db_index=True)
    group_id = models.UUIDField(null=True, blank=True, db_index=True)
    is_reversal = models.BooleanField(default=False)
    reversed_transaction = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reversal_children",
    )
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions_reversed",
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions_deleted",
    )
    
    objects = TransactionManager()
    all_objects = models.Manager()

    class Meta:
        indexes = [
            models.Index(fields=["account_source"]),
            models.Index(fields=["account_destination"]),
        ]

    def _populate_from_template(self):
        """Apply defaults from the selected template."""
        if self.template and self.template.autopop_map:   
            for field, default in self.template.autopop_map.items():
                if getattr(self, field) in (None, "", 0):
                    setattr(self, field, default)

    def _apply_defaults(self):
        """Fill the 4 dependent fields based on the chosen transaction_type."""
        key = (self.transaction_type or "").replace(" ", "_")
        try:
            tsrc, tdest, asrc, adest = transaction_type_TX_MAP[key]
        except KeyError:
            raise ValidationError({"transaction_type": "Unknown mapping—update TX_MAP."})

        self.transaction_type_source      = tsrc
        self.transaction_type_destination = tdest
        self.asset_type_source            = asrc
        self.asset_type_destination       = adest

    # auto-fill before validation *and* before saving
    def clean(self):
        self._populate_from_template()
        # Auto-map certain Outside transfers to Buy Acquisition when created
        # from the generic transaction form or API:
        # If destination account is Outside and either the entity source
        # equals the entity destination OR the user selected Transfer,
        # treat this as a Buy Acquisition so it correctly posts from Liquid
        # to Non‑Liquid.
        try:
            dest_is_outside = bool(
                getattr(self, "account_destination", None)
                and (
                    getattr(self.account_destination, "account_type", None) == "Outside"
                    or getattr(self.account_destination, "account_name", None) == "Outside"
                )
            )
        except Exception:
            dest_is_outside = False
        same_entity = (
            getattr(self, "entity_source_id", None)
            and getattr(self, "entity_destination_id", None)
            and self.entity_source_id == self.entity_destination_id
        )
        if dest_is_outside and (same_entity or (self.transaction_type or "").lower() == "transfer"):
            # Use the label form to satisfy model choices; mapping handles underscores
            self.transaction_type = "buy acquisition"

        self._apply_defaults()
        super().clean()

        # Prevent single-leg transactions from mixing currencies
        if (
            self.transaction_type != "transfer"
            and self.account_source
            and self.account_destination
        ):
            c1 = getattr(self.account_source, "currency_id", None)
            c2 = getattr(self.account_destination, "currency_id", None)
            if c1 and c2 and c1 != c2:
                raise ValidationError(
                    "Source and destination accounts must share the same currency."
                )

    def save(self, *args, **kwargs):
        # Ensure template defaults are applied first
        self._populate_from_template()
        self._apply_defaults()

        creating = self.pk is None
        
        account = None
        if self.transaction_type == "income" and self.account_destination_id:
            account = self.account_destination
        elif self.account_source_id:
            account = self.account_source
        elif self.account_destination_id:
            account = self.account_destination

        if creating:
            # assign posting timestamp
            self.posted_at = timezone.now()
            # compute seq per account ledger
            accounts = {self.account_source_id, self.account_destination_id}
            accounts.discard(None)
            next_seq = 0
            for acc_id in accounts:
                last = (
                    Transaction.all_objects
                    .filter(
                        Q(account_source_id=acc_id) | Q(account_destination_id=acc_id),
                        is_deleted=False,
                    )
                    .aggregate(Max("seq_account"))["seq_account__max"] or 0
                )
                if last > next_seq:
                    next_seq = last
            self.seq_account = next_seq + 1

        if not self.currency_id:
            # Loan.save and other callers may explicitly supply a currency. In
            # that case we must not infer a new one here; otherwise a loan
            # disbursed in KRW could be overwritten with the user's PHP base
            # currency and then converted back, inflating the displayed amount.
            if account and getattr(account, "currency_id", None):
                self.currency = account.currency
            elif self.user and getattr(self.user, "base_currency_id", None):
                self.currency = self.user.base_currency
            else:
                self.currency = Currency.objects.filter(code="PHP").first()
                
        super().save(*args, **kwargs)
        for acc_field in ["account_source", "account_destination"]:
            acc = getattr(self, acc_field, None)
            if acc and hasattr(acc, "credit_card"):
                bal = abs(acc.get_current_balance())
                card = acc.credit_card
                card.outstanding_amount = bal
                card.available_credit = (card.credit_limit or Decimal("0")) - bal
                card.save(update_fields=["outstanding_amount", "available_credit"])

    def delete(self, *args, **kwargs):
        acc_ids = [self.account_source_id, self.account_destination_id]
        result = super().delete(*args, **kwargs)
        for acc_id in acc_ids:
            if acc_id:
                acc = Account.objects.filter(pk=acc_id).first()
                if acc and hasattr(acc, "credit_card"):
                    bal = abs(acc.get_current_balance())
                    card = acc.credit_card
                    card.outstanding_amount = bal
                    card.available_credit = (card.credit_limit or Decimal("0")) - bal
                    card.save(update_fields=["outstanding_amount", "available_credit"])
        return result
