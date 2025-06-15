from django.db import models
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
from transactions.models import Transaction

# Create your models here.

class Asset(models.Model):
    """Simple asset record linked to buy/sell transactions."""

    name = models.CharField(max_length=255)
    purchase_tx = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name="asset_purchase",
    )
    sell_tx = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asset_sale",
    )

    created_at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assets", null=True)

    def __str__(self) -> str:
        return self.name

    @property
    def selling_date(self):
        """Return the date the asset was sold, if any."""
        if self.sell_tx:
            return self.sell_tx.date
        return None

    @property
    def price_sold(self):
        """Return the price the asset was sold for."""
        if not self.sell_tx:
            return None
        purchase_amt = self.purchase_tx.amount or Decimal("0")
        return purchase_amt + (self.sell_tx.amount or Decimal("0"))

    @property
    def profit(self):
        """Return the profit made from selling the asset."""
        if self.sell_tx:
            return self.sell_tx.amount or Decimal("0")
        return None