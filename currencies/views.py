from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
import logging

from . import services
from .models import Currency


logger = logging.getLogger(__name__)


@login_required
@require_POST
def set_currency(request):
    """Store the selected currency code in the session."""
    code = (request.POST.get("code") or "").upper()
    if Currency.objects.filter(code=code, is_active=True).exists():
        request.session["active_currency"] = code
        request.session["currency"] = code
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or request.META.get("HTTP_REFERER")
        or "/"
    )
    return redirect(next_url)


@login_required
def active_currencies(request):
    """Return JSON of active currencies for dropdowns."""
    data = list(
        Currency.objects.filter(is_active=True).values("id", "code", "name")
    )
    return JsonResponse({"currencies": data})


@login_required
def api_currencies(request):

    try:
        data = services.get_frankfurter_currencies()
        return JsonResponse(data)

    except services.CurrencySourceError:
        logger.exception("Unable to load currencies")
        return JsonResponse({}, status=502)