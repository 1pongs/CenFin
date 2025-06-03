from django.shortcuts import render
from django.db.models.functions import Coalesce
from django.db.models import Sum, F, Value, DecimalField
from decimal import Decimal

from accounts.models import Account
from transactions.models import Transaction

# Create your views here.
    

def account_list(request):
    qs = (
    Account.objects.active()
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
    .annotate(
        net_total=F("dest_total") - F("src_total")
    )
    .order_by("account_name")
    )
    return render(request, "accounts/account_list.html", {"accounts": qs})
