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

    total_balance = qs.aggregate(total=Sum("net_total"))["total"] or Decimal("0.00")

    context = {
        "accounts": qs,
        "search": search,
        "sort": sort,
        "total_balance": total_balance,
    }
    return render(request, "accounts/account_list.html", context)


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
        messages.success(request, "Account deleted.")
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
    def post(self, request, pk):
        acc = get_object_or_404(Account, pk=pk, user=request.user, is_active=False)
        acc.is_active = True
        acc.save()
        messages.success(request, "Account restored.")
        return redirect(reverse("accounts:archived"))


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