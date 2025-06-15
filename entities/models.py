from django.db import models
from django.conf import settings

# Create your models here.

class EntityQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

class Entity(models.Model):
    entities_type_choices = [
        ('account', 'Account'),
        ('investment', 'Investment'),
        ('emergency Fund','Emergency Fund'),
        ('business Fund','Business Fund'),
        ('retirement Fund', 'Retirement Fund'),
        ('educational Fund', 'Educational Fund'),
        ('outside', 'Outside'),
        ('others', 'Others'),
    ]
    entity_name = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, choices=entities_type_choices)
    is_active = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entities", null=True)

    objects=EntityQuerySet.as_manager()

    def delete(self, *args, **kwargs):
        self.is_active=False
        self.save()

    def __str__(self):
        return self.entity_name

    def current_balance(self):
        """Return current balance for this entity."""
        from django.db.models import Sum
        from decimal import Decimal
        from transactions.models import Transaction

        inflow = (
            Transaction.objects.filter(entity_destination=self)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0")
        )
        outflow = (
            Transaction.objects.filter(entity_source=self)
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0")
        )
        return inflow - outflow