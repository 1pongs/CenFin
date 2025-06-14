from django.db import models
from django.utils import timezone
from django.conf import settings
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

