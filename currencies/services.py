import logging
from typing import Dict

import requests
from django.core.cache import cache

from .models import Currency

logger = logging.getLogger(__name__)

FRANKFURTER_CACHE_KEY = "frankfurter_currencies"
FRANKFURTER_CACHE_TIMEOUT = 24 * 60 * 60  # 1 day


class CurrencySourceError(Exception):
    """Raised when an external currency source fails."""

    pass

def _map_existing(currencies: Dict[str, str]) -> Dict[str, str]:
    """Return subset of currencies that exist in the DB."""
    codes = list(currencies.keys())
    existing = set(
        Currency.objects.filter(code__in=codes, is_active=True).values_list("code", flat=True)
    )
    return {c: n for c, n in currencies.items() if c in existing}


def get_rem_a_currencies() -> Dict[str, str]:
    """Return currencies supported by Remittance Center A."""
    currencies = {
        "USD": "US Dollar",
        "PHP": "Philippine Peso",
        "EUR": "Euro",
        "JPY": "Japanese Yen",
    }
    return _map_existing(currencies)


def get_frankfurter_currencies() -> Dict[str, str]:
    """Fetch and cache list of currencies from Frankfurter."""
    cached = cache.get(FRANKFURTER_CACHE_KEY)
    if cached:
        return cached

    try:
        resp = requests.get("https://api.frankfurter.dev/v1/currencies", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected response")
    except Exception as exc:  # pragma: no cover - network error path
        logger.exception("Failed to fetch Frankfurter currencies: %s", exc)
        if cached:
            return cached
        raise CurrencySourceError("Frankfurter unavailable") from exc

    mapped = _map_existing(data)
    cache.set(FRANKFURTER_CACHE_KEY, mapped, FRANKFURTER_CACHE_TIMEOUT)
    return mapped