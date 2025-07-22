from django.db import models
from django.conf import settings

# Create your models here.

class EntityQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

class Entity(models.Model):
    entities_type_choices = [
        ('free fund', 'Free Fund'),
        ('investment fund', 'Investment Fund'),
        ('emergency fund', 'Emergency Fund'),
        ('business fund', 'Business Fund'),
        ('retirement fund', 'Retirement Fund'),
        ('educational fund', 'Educational Fund'),
        ('outside', 'Outside'),
        ('personal fund', 'Personal Fund'),
    ]
    entity_name = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, choices=entities_type_choices)
    is_active = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    system_hidden = models.BooleanField(default=False)
    is_account_entity = models.BooleanField(default=False)
    is_system_default = models.BooleanField(default=False, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entities", null=True)

    objects=EntityQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self._state.adding:
            qs = Entity.objects.filter(entity_name__iexact=self.entity_name, user=self.user)
            if qs.filter(is_active=True).exists():
                from django.core.exceptions import ValidationError
                raise ValidationError({"entity_name": "Name already in use."})
            inactive = qs.filter(is_active=False).first()
            if inactive:
                self.pk = inactive.pk
                self.is_active = True
                self._state.adding = False
        else:
            if self.is_system_default:
                from django.db.models import ProtectedError
                orig = Entity.objects.get(pk=self.pk)
                if orig.entity_name != self.entity_name or orig.is_active != self.is_active:
                    raise ProtectedError("System entity cannot be modified", [self])
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_system_default:
            from django.db.models import ProtectedError
            raise ProtectedError("System entity cannot be modified", [self])
        self.is_active = False
        self.save()

    def __str__(self):
        return self.entity_name

    def current_balance(self):
        """Return current balance for this entity."""
        from django.db.models import Sum, Case, When, F, DecimalField
        from decimal import Decimal
        from transactions.models import Transaction

        inflow = (
            Transaction.all_objects.filter(
                entity_destination=self,
                asset_type_destination__iexact="liquid",
                child_transfers__isnull=True,
            )
            .aggregate(
                total=Sum(
                    Case(
                        When(destination_amount__isnull=False, then=F("destination_amount")),
                            default=F("amount"),
                        output_field=DecimalField(),
                    )
                )
            )
            .get("total")
            or Decimal("0")
        )
        outflow = (
            Transaction.all_objects.filter(
                entity_source=self,
                asset_type_source__iexact="liquid",
                child_transfers__isnull=True,
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or Decimal("0")
        )
        return inflow - outflow