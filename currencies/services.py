import logging
from typing import Dict

import requests
from django.core.cache import cache
from .models import Currency

logger = logging.getLogger(__name__)


class CurrencySourceError(Exception):
    """Raised when an external currency source fails."""
    pass


_FRANK_URL = "https://api.frankfurter.dev/v1/currencies"
_CACHE_KEY = "frankfurter_currencies"
_TTL       = 86_400            # 24 h


def _limit_to_active(currencies: Dict[str, str]) -> Dict[str, str]:
    """
    Keep only codes that exist in the DB AND are marked is_active=True.
    If none are found (e.g. dev DB is empty), return the full dict so
    the dropdowns are never blank.
    """
    codes = list(currencies)
    active_codes = set(
        Currency.objects.filter(code__in=codes, is_active=True)
                        .values_list("code", flat=True)
    )
    if active_codes:
        return {c: n for c, n in currencies.items() if c in active_codes}
    return currencies   # dev fallback → give everything


def get_rem_a_currencies() -> Dict[str, str]:
    """Hard-coded list for Remittance Center A, filtered as above."""
    raw = {
        "USD": "US Dollar",
        "PHP": "Philippine Peso",
        "EUR": "Euro",
        "JPY": "Japanese Yen",
    }
    return _limit_to_active(raw)


def get_frankfurter_currencies() -> Dict[str, str]:
    """Fetch (and cache) the Frankfurter currency map."""
    if cached := cache.get(_CACHE_KEY):
        return cached

    try:
        resp = requests.get(_FRANK_URL, timeout=10)
        resp.raise_for_status()
        raw = resp.json()                 # Frankfurter  TOP-LEVEL dict
        if not isinstance(raw, dict):
            raise ValueError("unexpected response shape")
    except Exception as exc:              # network / JSON error
        logger.exception("Frankfurter fetch failed: %s", exc)
        raise CurrencySourceError("Frankfurter unavailable") from exc

    mapped = _limit_to_active(raw)
    cache.set(_CACHE_KEY, mapped, _TTL)
    return mapped