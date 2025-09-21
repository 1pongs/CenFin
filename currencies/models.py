from django.db import models


class Currency(models.Model):
    """Simple ISO currency model."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return self.code


class ExchangeRate(models.Model):
    """Exchange rate between two currencies."""

    currency_from = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="rates_from"
    )
    currency_to = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="rates_to"
    )
    rate = models.DecimalField(max_digits=12, decimal_places=6)

    class Meta:
        unique_together = (
            "currency_from",
            "currency_to",
        )

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"1 {self.currency_from} = {self.rate} {self.currency_to}"


def get_rate(currency_from, currency_to):
    """Return the exchange rate from currency_from to currency_to."""

    try:
        return ExchangeRate.objects.get(
            currency_from=currency_from,
            currency_to=currency_to,
        ).rate
    except ExchangeRate.DoesNotExist:
        return None
