from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from decimal import Decimal
from datetime import date


def _add_months(d: date, months: int) -> date:
    """Return date d plus a number of months."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)

from transactions.models import Transaction


class Lender(models.Model):
    """Simple lender / issuer record."""
    name = models.CharField(max_length=100, unique=True)

    def save(self, *args, **kwargs):
        if self._state.adding:
            if Lender.objects.filter(name__iexact=self.name).exists():
                raise ValidationError({"name": "Lender with this name already exists."})
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("name"), name="uniq_lender_name_ci")
        ]


class Loan(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loans", null=True)
    lender = models.ForeignKey(Lender, on_delete=models.CASCADE, related_name="loans")
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True)
    received_date = models.DateField()
    term_months = models.PositiveIntegerField()
    maturity_date = models.DateField(blank=True, null=True)
    monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    outstanding_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    disbursement_tx = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_disbursement",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        new = self._state.adding
        from currencies.models import Currency
        if not self.currency:
            if self.user and getattr(self.user, "base_currency_id", None):
                self.currency = self.user.base_currency.code
            else:
                cur = Currency.objects.filter(code="PHP").first()
                if cur:
                    self.currency = cur.code
                else:
                    self.currency = "PHP"
        if not self.maturity_date and self.received_date and self.term_months:
            self.maturity_date = _add_months(self.received_date, self.term_months)
        if not self.term_months and self.received_date and self.maturity_date:
            self.term_months = (self.maturity_date.year - self.received_date.year) * 12 + (
                self.maturity_date.month - self.received_date.month
            )
        if self.monthly_payment is None and self.term_months:
            self.monthly_payment = (self.principal_amount / Decimal(self.term_months)).quantize(Decimal("0.01"))
        if new and not self.outstanding_balance:
            self.outstanding_balance = self.principal_amount
        super().save(*args, **kwargs)
        if new:
            self._create_schedule()
            from accounts.utils import ensure_outside_account
            from entities.utils import ensure_fixed_entities

            outside_acc = ensure_outside_account()
            outside_ent, account_ent = ensure_fixed_entities(self.user)
            tx = Transaction.objects.create(
                user=self.user,
                date=self.received_date,
                description=f"Loan from {self.lender.name}",
                transaction_type="loan_disbursement",
                amount=self.principal_amount,
                currency=Currency.objects.filter(code=self.currency).first(),
                account_source=outside_acc,
                account_destination=getattr(self, '_account_destination', None),
                entity_source=outside_ent,
                entity_destination=account_ent,
            )
            self.disbursement_tx = tx
            super().save(update_fields=["disbursement_tx"])
        else:
            if self.disbursement_tx_id:
                tx = self.disbursement_tx
                tx.date = self.received_date
                tx.amount = self.principal_amount
                tx.description = f"Loan from {self.lender.name}"
                tx.currency = Currency.objects.filter(code=self.currency).first()
                if getattr(self, "_account_destination", None) is not None:
                    tx.account_destination = self._account_destination
                if getattr(self, "_account_source", None) is not None:
                    tx.account_source = self._account_source
                if getattr(self, "_entity_source", None) is not None:
                    tx.entity_source = self._entity_source
                if getattr(self, "_entity_destination", None) is not None:
                    tx.entity_destination = self._entity_destination
                tx.save()
                
    def _create_schedule(self):
        for i in range(1, self.term_months + 1):
            due = _add_months(self.received_date, i)
            LoanPayment.objects.create(
                loan=self,
                due_date=due,
                amount=self.monthly_payment or Decimal("0"),
            )

    def __str__(self):
        return f"{self.lender.name} loan {self.principal_amount}"

    def delete(self, *args, **kwargs):
        tx_ids = []
        if self.disbursement_tx_id:
            tx_ids.append(self.disbursement_tx_id)
        tx_ids.extend(
            self.payments.filter(transaction_id__isnull=False)
            .values_list("transaction_id", flat=True)
        )
        from transactions.models import Transaction
        if tx_ids:
            Transaction.objects.filter(id__in=tx_ids).delete()
        super().delete(*args, **kwargs)

class LoanPayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="payments")
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True)

    def mark_paid(self, transaction):
        if not self.is_paid:
            self.transaction = transaction
            self.is_paid = True
            self.save()
            self.loan.outstanding_balance -= self.amount
            self.loan.save()

    def __str__(self):
        return f"Payment {self.due_date} - {self.amount}"


class CreditCard(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credit_cards", null=True)
    issuer = models.ForeignKey(Lender, on_delete=models.PROTECT, related_name="credit_cards")
    card_name = models.CharField(max_length=100)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True)
    statement_day = models.PositiveIntegerField()
    payment_due_day = models.PositiveIntegerField()
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    available_credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    account = models.OneToOneField(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="credit_card",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.card_name} ({self.issuer})"

    def save(self, *args, **kwargs):
        new = self._state.adding
        from currencies.models import Currency
        from accounts.models import Account

        if not self.currency:
            if self.user and getattr(self.user, "base_currency_id", None):
                self.currency = self.user.base_currency.code
            else:
                cur = Currency.objects.filter(code="PHP").first()
                self.currency = cur.code if cur else "PHP"
        
        default_cur = None
        if self.user and getattr(self.user, "base_currency_id", None):
            default_cur = self.user.base_currency
        else:
            default_cur = Currency.objects.filter(code="PHP").first()

        # If only updating balance fields, skip account management logic
        update_fields = kwargs.get("update_fields")
        if update_fields and set(update_fields).issubset({"outstanding_amount", "available_credit"}):
            self.available_credit = (self.credit_limit or Decimal("0")) - (
                self.outstanding_amount or Decimal("0")
            )
            return super().save(*args, **kwargs)
        
        if new:
            qs = Account.objects.filter(
                account_name__iexact=self.card_name,
                user=self.user,
            )
            if qs.filter(is_active=True).exists():
                raise ValidationError({"card_name": "Name already in use."})

            acc = qs.filter(is_active=False).first()
            cur_obj = Currency.objects.filter(code=self.currency).first()
            if acc:
                acc.is_active = True
                acc.account_type = "Credit"
                acc.currency = cur_obj or default_cur
                acc.save()
            else:
                acc = Account(
                    account_name=self.card_name,
                    account_type="Credit",
                    user=self.user,
                    currency=cur_obj or default_cur,
                )
                acc.save()
            self.account = acc
        else:
            acc = self.account
            if acc:
                if acc.account_name != self.card_name:
                    qs = Account.objects.filter(
                        account_name__iexact=self.card_name,
                        user=self.user,
                        is_active=True,
                    ).exclude(pk=acc.pk)
                    if qs.exists():
                        raise ValidationError({"card_name": "Name already in use."})
                    acc.account_name = self.card_name

                if acc.user != self.user:
                    acc.user = self.user

                if acc.account_type != "Credit":
                    acc.account_type = "Credit"

                if acc.currency_id is None or acc.currency.code != self.currency:
                    cur_obj = Currency.objects.filter(code=self.currency).first()
                    acc.currency = cur_obj or default_cur

                acc.save()
        # Keep available_credit derived from limit and outstanding balance
        self.available_credit = (self.credit_limit or Decimal("0")) - (
            self.outstanding_amount or Decimal("0")
        )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.account_id:
            self.account.delete()
        super().delete(*args, **kwargs)