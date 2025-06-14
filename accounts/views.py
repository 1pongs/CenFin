from django.shortcuts import render
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.db.models.functions import Coalesce
from django.db.models import Sum, F, Value, DecimalField
from decimal import Decimal

from accounts.models import Account
from .forms import AccountForm
from transactions.models import Transaction

# Create your views here.
    

def account_list(request):
    qs = (
    Account.objects.active().filter(user=request.user)
        .annotate(
            dest_total=Coalesce(
                Sum("transaction_as_destination__amount"),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
            src_total=Coalesce(
                Sum("transaction_as_source__amount"),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
        )
        .annotate(net_total=F("dest_total") - F("src_total"))
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

    total_balance = qs.aggregate(total=Sum("net_total"))[
        "total"
    ] or Decimal("0.00")

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
