"""Currency app public API."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from .views import set_currency, api_currencies  # re-export

__all__ = ["set_currency", "api_currencies"]

def set_currency(*args, **kwargs):
    from .views import set_currency as real
    return real(*args, **kwargs)


def api_currencies(*args, **kwargs):
    from .views import api_currencies as real
    return real(*args, **kwargs)