from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from datetime import date, timedelta
from django.db.models import Q

from cenfin_proj.utils import get_monthly_cash_flow_range, parse_range_params
from transactions.models import Transaction
from utils.currency import get_active_currency, convert_to_base
from decimal import Decimal


@login_required
@require_GET
def dashboard_data(request):
    """Return dashboard chart data filtered by entity and date range."""
    ent = request.GET.get('entity_id')
    # Ensure we always have a valid range; default to last 12 months
    start, end = parse_range_params(request, None)
    today = date.today()
    if not end:
        end = today
    if not start:
        year_ago = today.replace(day=1) - timedelta(days=365)
        start = date(year_ago.year, year_ago.month, 1)

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


@login_required
@require_GET
def category_summary(request):
    """Return per-category totals for income or expenses within a date range.

    Query params:
    - type: 'expense' (default) or 'income'
    - entities: comma-separated entity IDs to filter (optional)
    - start, end: YYYY-MM-DD (optional)
    - limit: top N categories to return (optional)
    """
    mode = request.GET.get('type', 'expense')
    entity_ids = request.GET.getlist('entities')
    if len(entity_ids) == 1 and ',' in entity_ids[0]:
        entity_ids = [e for e in entity_ids[0].split(',') if e]
    ids = []
    for val in entity_ids:
        try:
            ids.append(int(val))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid entity'}, status=400)
    start, end = parse_range_params(request, None)

    qs = Transaction.objects.filter(user=request.user, parent_transfer__isnull=True).prefetch_related('categories').select_related('currency', 'account_destination__currency')
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if ids:
        from django.db.models import Q
        qs = qs.filter(Q(entity_source_id__in=ids) | Q(entity_destination_id__in=ids))

    if mode == 'income':
        qs = qs.filter(transaction_type_destination__iexact='Income')
        def amount_and_currency(tx):
            if tx.destination_amount is not None and tx.account_destination and getattr(tx.account_destination, 'currency', None):
                return tx.destination_amount, tx.account_destination.currency
            return tx.amount, tx.currency
    else:
        qs = qs.filter(transaction_type_source__iexact='Expense')
        def amount_and_currency(tx):
            return tx.amount, tx.currency

    base_cur = get_active_currency(request)
    totals = {}
    for tx in qs:
        cats = list(tx.categories.all())
        if not cats:
            continue
        val, cur = amount_and_currency(tx)
        amt = convert_to_base(val or Decimal('0'), cur, base_cur, user=request.user)
        for c in cats:
            totals[c.name] = totals.get(c.name, Decimal('0')) + amt

    rows = sorted(({ 'name': k, 'total': float(v) } for k, v in totals.items()), key=lambda r: r['total'], reverse=True)
    try:
        limit = int(request.GET.get('limit') or 0)
        if limit > 0:
            rows = rows[:limit]
    except (TypeError, ValueError):
        pass
    return JsonResponse(rows, safe=False)


@login_required
@require_GET
def entity_summary(request):
    """Return per-entity totals for income, expenses, and net within a range.

    Query params: entities (subset to include), start, end. If no entities are
    provided, include all of the user's entities.
    """
    from entities.models import Entity
    start, end = parse_range_params(request, None)
    entity_ids = request.GET.getlist('entities')
    if len(entity_ids) == 1 and ',' in entity_ids[0]:
        entity_ids = [e for e in entity_ids[0].split(',') if e]
    ids = []
    for val in entity_ids:
        try:
            ids.append(int(val))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid entity'}, status=400)

    ents = Entity.objects.active().filter(user=request.user)
    if ids:
        ents = ents.filter(id__in=ids)

    base_cur = get_active_currency(request)
    results = []
    for e in ents:
        q = Transaction.objects.filter(user=request.user, parent_transfer__isnull=True).select_related('currency', 'account_destination__currency')
        if start:
            q = q.filter(date__gte=start)
        if end:
            q = q.filter(date__lte=end)
        inc = exp = cap_in = cap_out = Decimal('0')
        for tx in q.filter(entity_destination=e, transaction_type_destination__iexact='Income'):
            val = tx.destination_amount if tx.destination_amount is not None and tx.account_destination and getattr(tx.account_destination, 'currency', None) else tx.amount
            cur = tx.account_destination.currency if tx.destination_amount is not None and tx.account_destination and getattr(tx.account_destination, 'currency', None) else tx.currency
            inc += convert_to_base(val or 0, cur, base_cur, user=request.user)
        for tx in q.filter(entity_source=e, transaction_type_source__iexact='Expense'):
            exp += convert_to_base(tx.amount or 0, tx.currency, base_cur, user=request.user)
        for tx in q.filter(entity_destination=e, transaction_type__iexact='transfer'):
            val = tx.destination_amount if tx.destination_amount is not None and tx.account_destination and getattr(tx.account_destination, 'currency', None) else tx.amount
            cur = tx.account_destination.currency if tx.destination_amount is not None and tx.account_destination and getattr(tx.account_destination, 'currency', None) else tx.currency
            cap_in += convert_to_base(val or 0, cur, base_cur, user=request.user)
        for tx in q.filter(entity_source=e, transaction_type__iexact='transfer'):
            cap_out += convert_to_base(tx.amount or 0, tx.currency, base_cur, user=request.user)
        results.append({
            'entity': e.entity_name,
            'income': float(inc),
            'expenses': float(exp),
            'capital': float(cap_in - cap_out),
            'net': float(inc - exp),
        })
    return JsonResponse(results, safe=False)
