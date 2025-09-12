from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, UpdateView, DeleteView, TemplateView, View
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models.functions import Coalesce
from django.db.models import Sum, F, Value, DecimalField
from decimal import Decimal

from accounts.models import Account
from utils.currency import get_active_currency
from utils.conversion import convert_amount, MissingRateError
from django.conf import settings
from .forms import AccountForm
from transactions.models import Transaction

# Create your views here.
    

def account_list(request):
    qs = (
        Account.objects.active()
        .filter(user=request.user, is_visible=True)
        .with_current_balance()
        .annotate(net_total=F("current_balance"))
    )

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(account_name__icontains=search)

    sort = request.GET.get("sort", "name")
    if sort == "balance":
        qs = qs.order_by("-net_total")
    elif sort == "account_type":
        qs = qs.order_by("account_type", "account_name")
    else:
        qs = qs.order_by("account_name")
        
    active_cur = get_active_currency(request)
    base_cur = active_cur.code if active_cur else None
    converted = []
    total_balance = sum(c or Decimal("0") for _, c in converted)
    if base_cur:
        for a in qs:
            conv = a.balance_in_currency(base_cur)
            converted.append((a, conv))
            if conv is not None:
                total_balance += conv
    else:
        converted = [(a, None) for a in qs]

        total_balance = qs.aggregate(total=Sum("net_total"))["total"] or Decimal("0.00")

    context = {
        "accounts_converted": converted,
        "search": search,
        "sort": sort,
        "total_balance": total_balance,
        "base_currency": base_cur,
    }
    return render(request, "accounts/account_list.html", context)


class AccountDetailView(TemplateView):
    template_name = "accounts/account_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        account = get_object_or_404(Account, pk=self.kwargs["pk"], user=self.request.user)
        disp_code = getattr(self.request, "display_currency", settings.BASE_CURRENCY)
        bal = account.get_current_balance()
        try:
            converted = convert_amount(bal, account.currency.code, disp_code)
        except MissingRateError:
            converted = bal
        ctx["account"] = account
        ctx["converted_balance"] = converted
        return ctx


class AccountCreateView(CreateView):
    model = Account
    form_class = AccountForm
    template_name = "accounts/account_form.html"
    success_url = reverse_lazy("accounts:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class AccountUpdateView(UpdateView):
    model = Account
    form_class = AccountForm
    template_name = "accounts/account_form.html"
    success_url = reverse_lazy("accounts:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Account updated successfully!")
        return response


class AccountDeleteView(DeleteView):
    model = Account
    template_name = "accounts/account_confirm_delete.html"
    success_url = reverse_lazy("accounts:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.delete()
        restore_url = reverse("accounts:restore", args=[obj.pk])
        messages.success(request, "Account deleted. " + f"<a href=\"{restore_url}\" class=\"ms-2\">Undo</a>", extra_tags="safe")
        return redirect(self.success_url)


class AccountArchivedListView(TemplateView):
    template_name = "accounts/account_archived_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["accounts"] = Account.objects.filter(
            user=self.request.user, is_active=False
        )
        return ctx


class AccountRestoreView(View):
    def _restore(self, request, pk):
        acc = get_object_or_404(Account, pk=pk, user=request.user, is_active=False)
        acc.is_active = True
        acc.save()
        messages.success(request, "Account restored.")
        return redirect(reverse("accounts:archived"))
    
    def post(self, request, pk):
        return self._restore(request, pk)

    def get(self, request, pk):
        return self._restore(request, pk)


@require_POST
def api_create_account(request):
    """Create an account via AJAX."""
    form = AccountForm(request.POST)
    if form.is_valid():
        acc = form.save(commit=False)
        acc.user = request.user
        acc.save()
        return JsonResponse({"id": acc.pk, "name": acc.account_name})
    return JsonResponse({"errors": form.errors}, status=400)
