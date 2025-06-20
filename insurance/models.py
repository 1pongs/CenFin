from django.db import models
from django.conf import settings
from django.db.models import Sum, F, Value, Case, When
from django.db.models.functions import Coalesce
from decimal import Decimal


class InsuranceQuerySet(models.QuerySet):
    def with_cash_value(self):
        return self.annotate(
            cash_value=Case(
                When(
                    insurance_type="vul",
                    then=F("unit_balance") * F("unit_value"),
                ),
                default=Value(Decimal("0")),
                output_field=models.DecimalField(max_digits=18, decimal_places=6),
            )
        )

    def with_total_premiums_paid(self):
        return self.annotate(
            total_premiums_paid=Coalesce(
                Sum("premiums__amount"), Value(Decimal("0"))
            )
        )


class Insurance(models.Model):
    TYPE_CHOICES = [
        ("term", "Term"),
        ("whole", "Whole"),
        ("health", "Health"),
        ("vul", "VUL"),
    ]

    MODE_CHOICES = [
        ("annual", "Annual"),
        ("semiannual", "Semi-Annual"),
        ("quarterly", "Quarterly"),
        ("monthly", "Monthly"),
    ]

    STATUS_CHOICES = [
        ("inactive", "Inactive"),
        ("active", "Active"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="insurances",
        null=True,
    )
    policy_owner = models.CharField(max_length=255, blank=True)
    person_insured = models.CharField(max_length=255, blank=True)
    insurance_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    sum_assured = models.DecimalField(max_digits=18, decimal_places=2)
    premium_mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    premium_amount = models.DecimalField(max_digits=18, decimal_places=2)
    unit_balance = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    unit_value = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    valuation_date = models.DateField(null=True, blank=True)
    entity = models.ForeignKey(
        'entities.Entity', on_delete=models.CASCADE, null=True, blank=True, related_name='insurances'
    )
    acquisition = models.ForeignKey(
        'acquisitions.Acquisition', on_delete=models.CASCADE, null=True, blank=True, related_name='insurances'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="inactive")

    objects = InsuranceQuerySet.as_manager()

    class Meta:
        db_table = "insurance_insurance"

    def __str__(self) -> str:  # pragma: no cover - simple repr
        label = self.get_insurance_type_display()
        owner = self.policy_owner or self.person_insured
        return f"{label} for {owner}" if owner else label

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("insurance:detail", args=[self.pk])

    @property
    def cash_value(self):
        if self.insurance_type == "vul" and self.unit_balance and self.unit_value:
            return self.unit_balance * self.unit_value
        return Decimal("0")

    @property
    def total_premiums_paid(self):
        total = self.premiums.aggregate(total=Sum("amount")).get("total")
        return total or Decimal("0")


class PremiumPayment(models.Model):
    insurance = models.ForeignKey(
        Insurance, related_name="premiums", on_delete=models.CASCADE
    )
    date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    transaction = models.ForeignKey(
        'transactions.Transaction',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='premium_payments',
    )

    class Meta:
        db_table = "insurance_premiumpayment"

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"{self.insurance} - {self.amount}"