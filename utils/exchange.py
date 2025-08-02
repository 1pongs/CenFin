from decimal import Decimal
from django.db.models import OuterRef, Subquery
import requests

from currencies.models import Currency, ExchangeRate


def frankfurter_rate(code_from: str, code_to: str) -> Decimal:
    """Return the conversion rate from ``code_from`` to ``code_to``.

    If the rate is stored in the ``ExchangeRate`` table it is used. Otherwise a
    request is made to the Frankfurter API and the rate is cached in the
    database. The returned value is a :class:`~decimal.Decimal`.
    """
    code_from = code_from.upper()
    code_to = code_to.upper()
    if code_from == code_to:
        return Decimal("1")

    try:
        rate_obj = ExchangeRate.objects.get(
            currency_from__code=code_from, currency_to__code=code_to
        )
        return rate_obj.rate
    except ExchangeRate.DoesNotExist:
        pass

    resp = requests.get(
        f"https://api.frankfurter.app/latest?from={code_from}&to={code_to}",
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    rate_val = Decimal(str(data["rates"][code_to]))

    cur_from, _ = Currency.objects.get_or_create(code=code_from, defaults={"name": code_from})
    cur_to, _ = Currency.objects.get_or_create(code=code_to, defaults={"name": code_to})
    ExchangeRate.objects.update_or_create(
        currency_from=cur_from, currency_to=cur_to, defaults={"rate": rate_val}
    )
    return rate_val


def get_rate_subquery(to_code: str):
    """Return a subquery selecting the rate to ``to_code``.

    Used for annotating querysets with conversion rates without hitting the API
    inside templates.
    """
    return ExchangeRate.objects.filter(
        currency_from_id=OuterRef("currency_id"),
        currency_to__code=to_code,
    ).values("rate")[:1]