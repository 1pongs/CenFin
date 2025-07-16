from django.db import models
from django.conf import settings


class Currency(models.Model):
    """Simple ISO currency model."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return self.code


RATE_SOURCE_CHOICES = [
    ("USER", "User-defined"),
    ("FRANKFURTER", "Frankfurter"),
    ("REM_A", "Remittance Center A"),
]


class ExchangeRate(models.Model):
    """Exchange rate between two currencies."""

    source = models.CharField(max_length=20, choices=RATE_SOURCE_CHOICES)
    currency_from = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="rates_from"
    )
    currency_to = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="rates_to"
    )
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="exchange_rates",
    )

    class Meta:
        unique_together = (
            "source",
            "currency_from",
            "currency_to",
            "user",
        )

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"1 {self.currency_from} = {self.rate} {self.currency_to}"


def get_rate(currency_from, currency_to, source, user=None):
    """Return the exchange rate from currency_from to currency_to."""

    try:
        return ExchangeRate.objects.get(
            source=source,
            currency_from=currency_from,
            currency_to=currency_to,
            user=user,
        ).rate
    except ExchangeRate.DoesNotExist:
        if source == "USER":
            # when using user-defined rates, do not fall back
            return None
        if user is not None:
            # fall back to default (user=None)
            return get_rate(currency_from, currency_to, source, None)
        return None