from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from datetime import date
from django.db.models import Q

from cenfin_proj.utils import get_monthly_cash_flow_range, parse_range_params
from transactions.models import Transaction
from utils.currency import get_active_currency, convert_to_base


@login_required
@require_GET
def dashboard_data(request):
    """Return dashboard chart data filtered by entity and date range."""
    ent = request.GET.get('entity_id')
    start, end = parse_range_params(request, None)

    if ent and ent not in {'all', 'overall'}:
        try:
            ent = int(ent)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid entity'}, status=400)
    else:
        ent = None

    base_cur = get_active_currency(request)
    data = get_monthly_cash_flow_range(
        ent, start=start, end=end, drop_empty=False, user=request.user, currency=base_cur
    )

    labels = [row['month'] for row in data]
    datasets = {
        'income': [float(row['income']) for row in data],
        'expenses': [float(row['expenses']) for row in data],
        'liquid': [float(row['liquid']) for row in data],
        'asset': [float(row['non_liquid']) for row in data],
    }

    return JsonResponse({'labels': labels, 'datasets': datasets})


@login_required
@require_GET
def top10_data(request):
    """Return top-10 big ticket entries filtered by entity and type."""
    entity_ids = request.GET.getlist("entities")
    if len(entity_ids) == 1 and "," in entity_ids[0]:
        entity_ids = [e for e in entity_ids[0].split(",") if e]
    txn_type = request.GET.get("txn_type")
    ids = []
    for val in entity_ids:
        try:
            ids.append(int(val))
        except (TypeError, ValueError):
            return JsonResponse({"error": "invalid entity"}, status=400)

    today = date.today()
    start, end = parse_range_params(request, date(today.year, 1, 1))

    qs = Transaction.objects.filter(user=request.user, date__range=[start, end]).select_related("currency")
    if ids:
        qs = qs.filter(Q(entity_source_id__in=ids) | Q(entity_destination_id__in=ids))
    if txn_type and txn_type != "all":
        qs = qs.filter(transaction_type=txn_type)
    base_cur = get_active_currency(request)
    entries = []
    for tx in qs:
        amt = convert_to_base(abs(tx.amount or 0), tx.currency, base_cur, user=request.user)
        if tx.transaction_type_destination == "Income":
            entry_type = "income"
        elif tx.transaction_type_source == "Expense":
            entry_type = "expense"
        elif tx.asset_type_destination == "Non-Liquid":
            entry_type = "asset"
        else:
            entry_type = "other"
        entries.append({"label": tx.description, "amount": amt, "type": entry_type})

    entries.sort(key=lambda r: r["amount"], reverse=True)
    top = entries[:10]
    payload = {
       "labels": [r["label"] for r in top],
        "amounts": [float(r["amount"]) for r in top],
        "types": [r["type"] for r in top],
    }
    return JsonResponse(payload)