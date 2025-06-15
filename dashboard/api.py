from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from cenfin_proj.utils import get_monthly_cash_flow


@login_required
@require_GET
def dashboard_data(request):
    """Return dashboard chart data filtered by entity and months."""
    ent = request.GET.get('entity_id')
    months = request.GET.get('months', '12')

    if ent and ent != 'all':
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
        'nonliquid': [float(row['non_liquid']) for row in data],
        'net_worth': [float(row['liquid'] + row['non_liquid']) for row in data],
    }

    return JsonResponse({'labels': labels, 'datasets': datasets})
