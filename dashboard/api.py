from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from datetime import date
from django.db.models import Sum, Case, When, F, Value, CharField
from django.db.models.functions import Abs
from django.db.models import Q
from cenfin_proj.utils import get_monthly_cash_flow_range, parse_range_params
from transactions.models import Transaction


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

    data = get_monthly_cash_flow_range(ent, start=start, end=end, drop_empty=False, user=request.user)

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

    qs = Transaction.objects.filter(user=request.user, date__range=[start, end])
    if ids:
        qs = qs.filter(Q(entity_source_id__in=ids) | Q(entity_destination_id__in=ids))
    if txn_type and txn_type != "all":
        qs = qs.filter(transaction_type=txn_type)
    qs = (
        qs
        .annotate(entry_type=Case(
            When(transaction_type_destination="Income", then=Value("income")),
            When(transaction_type_source="Expense", then=Value("expense")),
            When(asset_type_destination="Non-Liquid", then=Value("asset")),
            default=Value("other"),
            output_field=CharField(),
        ))
        .annotate(abs_amount=Abs("amount"))
        .values("description", "entry_type")
        .annotate(total=Sum("abs_amount"))
        .order_by("-total")[:10]
    )

    payload = {
        "labels": [r["description"] for r in qs],
        "amounts": [float(r["total"]) for r in qs],
        "types": [r["entry_type"] for r in qs],
    }
    return JsonResponse(payload)