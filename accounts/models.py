from django.db import models
from django.conf import settings
from django.db.models.functions import Coalesce, Lower
from django.db.models import Q
from currencies.models import Currency, RATE_SOURCE_CHOICES, get_rate


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
        ('Crypto Wallet', 'Crypto Wallet'),
        ('Entity','Entity'),
        ('Credit', 'Credit'),
        ('Outside','Outside'),
    ]
    account_name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=50, choices=account_type_choices)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="accounts",
        null=True,
    )
    is_active = models.BooleanField(default=True)
    is_visible = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts", null=True)

    objects = AccountManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("account_name"),
                "user",
                condition=Q(is_active=True),
                name="uniq_account_name_user_active_ci",
            )
        ]

    def save(self, *args, **kwargs):
        force_insert = kwargs.pop("force_insert", False)
        if self.currency_id is None:
            default_cur = None
            if self.user and getattr(self.user, "base_currency_id", None):
                default_cur = self.user.base_currency
            else:
                default_cur = Currency.objects.filter(code="PHP").first()
            self.currency = default_cur
        
        if self._state.adding:
            qs = Account.objects.filter(account_name__iexact=self.account_name, user=self.user)
            if qs.filter(is_active=True).exists():
                from django.core.exceptions import ValidationError
                raise ValidationError({"account_name": "Name already in use."})
            inactive = qs.filter(is_active=False).first()
            if inactive:
                self.pk = inactive.pk
                self.is_active = True
                self._state.adding = False
        super().save(force_insert=force_insert if self._state.adding else False, *args, **kwargs)

    def delete(self, *args, **kwargs):
        self.is_active=False
        self.save()

    def __str__(self):
        if self.account_type == "Credit" and hasattr(self, "credit_card"):
            limit = self.credit_card.credit_limit
            cur = self.currency.code if self.currency else ""
            return f"{self.account_name} — {limit:,.0f} {cur} limit".strip()
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

    def balance_in_currency(self, currency_code, source=None):
        """Return balance converted to the given currency."""
        if source is None and hasattr(self.user, "preferred_rate_source"):
            source = self.user.preferred_rate_source
        target = Currency.objects.get(code=currency_code)
        rate = get_rate(self.currency, target, source, self.user)
        if rate is None:
            return None
        return self.get_current_balance() * rate