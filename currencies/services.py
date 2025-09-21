import logging
from typing import Dict

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


class CurrencySourceError(Exception):
    """Raised when an external currency source fails."""

    pass


_FRANK_URL = "https://api.frankfurter.app/currencies"
_CACHE_KEY = "frankfurter_currencies"
_TTL = 86_400  # 24 h
_UNAVAIL_KEY = _CACHE_KEY + "_unavailable"
_UNAVAIL_TTL = 300  # 5 minutes: suppress retry attempts for this period


def get_frankfurter_currencies() -> Dict[str, str]:
    """Fetch (and cache) the Frankfurter currency map."""
    # If a recent failure was recorded, avoid retrying for a short period.
    if cache.get(_UNAVAIL_KEY):
        raise CurrencySourceError("Frankfurter temporarily unavailable")

    if cached := cache.get(_CACHE_KEY):
        return cached

    try:
        resp = requests.get(_FRANK_URL, timeout=10)
        resp.raise_for_status()
        raw = resp.json()  # Frankfurter  TOP-LEVEL dict
        if not isinstance(raw, dict):
            raise ValueError("unexpected response shape")
    except Exception as exc:  # network / JSON error
        # Record a short-lived marker so we don't hammer the remote API on
        # subsequent requests. The context processor will catch the
        # CurrencySourceError and fall back to local DB entries.
        try:
            cache.set(_UNAVAIL_KEY, True, _UNAVAIL_TTL)
        except Exception:
            # Cache failures are non-fatal; proceed to raise so callers can
            # still fall back.
            pass
        logger.warning(
            "Frankfurter fetch failed: %s; suppressing retries for %s seconds",
            exc,
            _UNAVAIL_TTL,
        )
        raise CurrencySourceError("Frankfurter unavailable") from exc

    cache.set(_CACHE_KEY, raw, _TTL)
    return raw
