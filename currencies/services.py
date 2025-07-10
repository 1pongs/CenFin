import os
import logging
from typing import List, Dict

import requests
from django.core.cache import cache

from .models import Currency

logger = logging.getLogger(__name__)

XE_CACHE_KEY = "xe_currency_list"
XE_CACHE_TIMEOUT = 24 * 60 * 60  # 1 day


def _map_existing(currencies: List[Dict[str, str]]) -> List[Dict[str, str]]:
    codes = [c.get("code") for c in currencies if c.get("code")]
    mapping = {c.code: c.id for c in Currency.objects.filter(code__in=codes, is_active=True)}
    result = []
    for cur in currencies:
        cid = mapping.get(cur.get("code"))
        if cid:
            result.append({"id": cid, "code": cur["code"], "name": cur.get("name", "")})
    return result


def get_rc_a_currencies() -> List[Dict[str, str]]:
    """Return currencies supported by Remittance Center A."""
    currencies = [
        {"code": "USD", "name": "US Dollar"},
        {"code": "PHP", "name": "Philippine Peso"},
        {"code": "EUR", "name": "Euro"},
        {"code": "JPY", "name": "Japanese Yen"},
    ]
    return _map_existing(currencies)


def get_xe_currencies() -> List[Dict[str, str]]:
    """Fetch and cache list of currencies from XE.com."""
    cached = cache.get(XE_CACHE_KEY)
    if cached:
        return cached

    key = os.getenv("XE_API_KEY")
    if not key:
        raise RuntimeError("XE_API_KEY not configured")

    if ":" in key:
        account_id, api_key = key.split(":", 1)
        auth = (account_id, api_key)
    else:
        auth = (key, "")

    try:
        resp = requests.get("https://xecdapi.xe.com/v1/currencies.json", auth=auth, timeout=10)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover - network error path
        logger.exception("Failed to fetch XE currencies: %s", exc)
        raise

    data = resp.json().get("currencies")
    currencies = []
    if isinstance(data, dict):
        for code, name in data.items():
            currencies.append({"code": code, "name": name})
    elif isinstance(data, list):
        for item in data:
            code = item.get("iso") or item.get("currency") or item.get("code")
            name = item.get("name") or item.get("currency_name") or item.get("description")
            if code:
                currencies.append({"code": code, "name": name or code})

    mapped = _map_existing(currencies)
    cache.set(XE_CACHE_KEY, mapped, XE_CACHE_TIMEOUT)
    return mapped