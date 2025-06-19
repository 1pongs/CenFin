from django.db import models
from django.conf import settings
from django.db.models.functions import Coalesce

# Create your models here.

class AccountQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)
    
    def with_current_balance(self):
        """Annotate accounts with their current balance."""
        from decimal import Decimal
        from django.db.models import (
            Sum,
            Case,
            When,
            F,
            DecimalField,
            Value,
            Q,
            OuterRef,
            Subquery,
        )

        from transactions.models import Transaction

        inflow_sq = (
            Transaction.objects.filter(account_destination_id=OuterRef("pk"))
            .values("account_destination_id")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        outflow_sq = (
            Transaction.objects.filter(account_source_id=OuterRef("pk"))
            .values("account_source_id")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        return (
            self.annotate(
                inflow=Coalesce(Subquery(inflow_sq, output_field=DecimalField()), Value(Decimal("0"))),
                outflow=Coalesce(Subquery(outflow_sq, output_field=DecimalField()), Value(Decimal("0"))),
            ).annotate(current_balance=F("inflow") - F("outflow"))
        )

class AccountManager(models.Manager):
    def get_queryset(self):
        return AccountQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def with_current_balance(self):
        return self.get_queryset().with_current_balance()


class Account(models.Model):
    account_type_choices = [
        ('Banks', 'Banks'),
        ('E-Wallet', 'E-Wallet'),
        ('Cash','Cash'),
        ('Outside','Outside'),
        ('Entity','Entity'),
    ]
    account_name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=50, choices=account_type_choices)
    is_active = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts", null=True)

    objects = AccountManager()

    def delete(self, *args, **kwargs):
        self.is_active=False
        self.save()

    def __str__(self):
        return self.account_name

    def get_current_balance(self):
        """Return the current balance for this account."""
        from decimal import Decimal
        
        val = (
            Account.objects.filter(pk=self.pk)
            .with_current_balance()
            .values_list("current_balance", flat=True)
            .first()
        )
        return val or Decimal("0")

    def current_balance(self):
        return self.get_current_balance()