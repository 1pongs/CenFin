from django.db import models
from django.utils import timezone
from accounts.models import Account
from entities.models import Entity
from django.db.models import JSONField
from django.core.exceptions import ValidationError
from .constants import transaction_type_TX_MAP

# Create your models here.

class TransactionTemplate(models.Model):
    name = models.CharField(max_length=60, unique=True)
    autopop_map = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return self.name

class Transaction(models.Model):
    template = models.ForeignKey(
        TransactionTemplate,
        null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    
    TRANSACTION_TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('buy asset', 'Buy Asset'),
        ('sell asset', 'Sell Asset'),
        ('transfer', 'Transfer'),
    ]

    date = models.DateField(default=timezone.now, null=True, blank=True,)
    description = models.CharField(max_length=255, null=True, blank=True,)

    account_source = models.ForeignKey(
        Account, on_delete=models.SET_NULL,
        related_name='transaction_as_source',
        null=True,
        blank=True,
        limit_choices_to={'is_active':True},
    )
    account_destination = models.ForeignKey(
        Account, on_delete=models.SET_NULL,
        related_name='transaction_as_destination',
        null=True,
        blank=True,
        limit_choices_to={'is_active':True},
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
    remarks = models.TextField(blank=True, null=True)

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

    def save(self, *args, **kwargs):
        self._populate_from_template()
        self._apply_defaults()
        super().save(*args, **kwargs)