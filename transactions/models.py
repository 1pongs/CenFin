from django.db import models
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from accounts.models import Account
from entities.models import Entity
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

class Transaction(models.Model):
    template = models.ForeignKey(
        TransactionTemplate,
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions", null=True)
    
    TRANSACTION_TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('premium_payment', 'Premium Payment'),
        ('buy acquisition', 'Buy Acquisition'),
        ('sell acquisition', 'Sell Acquisition'),
        ('transfer', 'Transfer'),
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
    categories = models.ManyToManyField(CategoryTag, related_name="transactions", blank=True)
    remarks = models.TextField(blank=True, null=True)

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

        acc_id = self.account_source_id
        ent_id = self.entity_source_id

    def save(self, *args, **kwargs):
        self._populate_from_template()
        self._apply_defaults()
        super().save(*args, **kwargs)
        for acc_field in ["account_source", "account_destination"]:
            acc = getattr(self, acc_field, None)
            if acc and hasattr(acc, "credit_card"):
                bal = abs(acc.get_current_balance())
                card = acc.credit_card
                card.current_balance = bal
                card.save(update_fields=["current_balance"])