from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
import logging

from . import services                # ← single import is enough
from users.access import AccessRequiredMixin
from .models import ExchangeRate, Currency
from .forms import ExchangeRateForm

logger = logging.getLogger(__name__)


@login_required
def api_currencies(request):
    """
    AJAX endpoint used by the Exchange-Rate form.
    Query-string:  ?source=FRANKFURTER | REM_A
    Returns JSON like {"USD": "United States Dollar", …}
    """
    source = (request.GET.get("source") or "").upper()

    try:
        if source == "FRANKFURTER":
            data = services.get_frankfurter_currencies()
        elif source == "REM_A":
            data = services.get_rem_a_currencies()
        else:
            data = {}
        return JsonResponse(data)

    except services.CurrencySourceError:
        logger.exception("Unable to load currencies")
        return JsonResponse({}, status=502)