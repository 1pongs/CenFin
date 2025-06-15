from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from datetime import date
from django.db.models import Sum, Case, When, F, Value, CharField
from django.db.models.functions import Abs
from django.db.models import Q
from cenfin_proj.utils import get_monthly_cash_flow
from transactions.models import Transaction


@login_required
@require_GET
def dashboard_data(request):
    """Return dashboard chart data filtered by entity and months."""
    ent = request.GET.get('entity_id')
    months = request.GET.get('months', '12')

    if ent and ent not in {'all', 'overall'}:
        try:
            ent = int(ent)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid entity'}, status=400)
    else:
        ent = None

    try:
        months = int(months)
    except (TypeError, ValueError):
        months = 12

    data = get_monthly_cash_flow(ent, months, drop_empty=False, user=request.user)

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
    """Return top-10 big ticket entries filtered by entity."""
    ent = request.GET.get('entity_id')
    if ent and ent not in {'overall', 'all'}:
        try:
            ent = int(ent)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid entity'}, status=400)
    else:
        ent = None

    today = date.today()
    year_start = date(today.year, 1, 1)

    q = Q(user=request.user, date__gte=year_start)
    if ent:
        q &= Q(entity_source_id=ent) | Q(entity_destination_id=ent)

    qs = (
        Transaction.objects.filter(q)
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