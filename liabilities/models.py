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
    statement_day = models.PositiveIntegerField()
    payment_due_day = models.PositiveIntegerField()
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.card_name} ({self.issuer})"