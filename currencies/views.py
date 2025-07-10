"""Views for managing exchange rates."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import logging
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.views.decorators.http import require_POST

from . import services

from users.access import AccessRequiredMixin
from .models import ExchangeRate, Currency
from .forms import ExchangeRateForm


class ExchangeRateListView(AccessRequiredMixin, ListView):
    model = ExchangeRate
    template_name = "currencies/rate_list.html"

    def get_queryset(self):
        qs = super().get_queryset().filter(user=self.request.user)
        return qs.order_by("currency_from__code", "currency_to__code")


class ExchangeRateCreateView(AccessRequiredMixin, CreateView):
    model = ExchangeRate
    form_class = ExchangeRateForm
    template_name = "currencies/rate_form.html"
    success_url = reverse_lazy("currencies:rate-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ExchangeRateUpdateView(AccessRequiredMixin, UpdateView):
    model = ExchangeRate
    form_class = ExchangeRateForm
    template_name = "currencies/rate_form.html"
    success_url = reverse_lazy("currencies:rate-list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class ExchangeRateDeleteView(AccessRequiredMixin, DeleteView):
    model = ExchangeRate
    template_name = "currencies/rate_confirm_delete.html"
    success_url = reverse_lazy("currencies:rate-list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)
    
    
@require_POST
def set_currency(request):
    """Update the active currency stored in the session."""
    code = request.POST.get("code")
    from .models import Currency
    if Currency.objects.filter(code=code, is_active=True).exists():
        request.session["currency"] = code
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
def active_currencies(request):
    """Return JSON of active currencies for dropdowns."""
    data = list(
        Currency.objects.filter(is_active=True).values("id", "code", "name")
    )
    return JsonResponse({"currencies": data})


logger = logging.getLogger(__name__)


@login_required
def api_currencies(request):
    """Return currencies for the given exchange rate source."""
    source = request.GET.get("source")
    try:
        if source == "FRANKFURTER":
            data = services.get_frankfurter_currencies()
        elif source == "REM_A":
            data = services.get_rem_a_currencies()
        else:
            data = {}
        return JsonResponse(data)
    except Exception:
        logger.exception("Unable to load currencies")
        return JsonResponse({}, status=502)