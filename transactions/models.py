from django.db import models
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from accounts.models import Account
from entities.models import Entity
from currencies.models import Currency
from django.db.models import JSONField
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
    transaction_type = models.CharField(max_length=20, choices=TXN_TYPE_CHOICES, blank=True, null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="category_tags")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "transaction_type", "user")

    def __str__(self):
        return self.name

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

        account = None
        if self.transaction_type == "income" and self.account_destination_id:
            account = self.account_destination
        elif self.account_source_id:
            account = self.account_source
        elif self.account_destination_id:
            account = self.account_destination

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