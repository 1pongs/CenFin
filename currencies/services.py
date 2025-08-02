import logging
from typing import Dict

import requests
from django.core.cache import cache
from .models import Currency

logger = logging.getLogger(__name__)


class CurrencySourceError(Exception):
    """Raised when an external currency source fails."""
    pass


_FRANK_URL = "https://api.frankfurter.app/currencies"
_CACHE_KEY = "frankfurter_currencies"
_TTL = 86_400  # 24 h

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

    cache.set(_CACHE_KEY, raw, _TTL)
    return raw