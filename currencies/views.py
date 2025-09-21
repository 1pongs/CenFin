from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.urls import reverse
import logging

from . import services
from .models import Currency


logger = logging.getLogger(__name__)


@login_required
@require_POST
def set_display_currency(request):
    """Store the selected display currency code in the session."""
    code = (request.POST.get("code") or "").upper()
    if code:
        Currency.objects.get_or_create(code=code, defaults={"name": code})
        request.session["display_currency"] = code
    referer = request.META.get("HTTP_REFERER") or reverse("dashboard:dashboard")
    return redirect(referer)


@login_required
def active_currencies(request):
    """Return JSON of active currencies for dropdowns."""
    data = list(Currency.objects.filter(is_active=True).values("id", "code", "name"))
    return JsonResponse({"currencies": data})


@login_required
def api_currencies(request):

    try:
        data = services.get_frankfurter_currencies()
        return JsonResponse(data)

    except services.CurrencySourceError:
        logger.exception("Unable to load currencies")
        return JsonResponse({}, status=502)
