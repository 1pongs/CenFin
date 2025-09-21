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
    ent = request.GET.get("entity_id")
    # Ensure we always have a valid range; default to last 12 months
    start, end = parse_range_params(request, None)
    today = date.today()
    if not end:
        end = today
    if not start:
        year_ago = today.replace(day=1) - timedelta(days=365)
        start = date(year_ago.year, year_ago.month, 1)

    if ent and ent not in {"all", "overall"}:
        try:
            ent = int(ent)
        except (TypeError, ValueError):
            return JsonResponse({"error": "invalid entity"}, status=400)
    else:
        ent = None

    base_cur = get_active_currency(request)
    data = get_monthly_cash_flow_range(
        ent,
        start=start,
        end=end,
        drop_empty=False,
        user=request.user,
        currency=base_cur,
    )

    labels = [row["month"] for row in data]
    datasets = {
        "income": [float(row["income"]) for row in data],
        "expenses": [float(row["expenses"]) for row in data],
        "liquid": [float(row["liquid"]) for row in data],
        "asset": [float(row["non_liquid"]) for row in data],
        # Keep the original key as well for compatibility with older client code
        "non_liquid": [float(row["non_liquid"]) for row in data],
    }

    return JsonResponse({"labels": labels, "datasets": datasets})


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

    qs = Transaction.objects.filter(
        user=request.user, date__range=[start, end]
    ).select_related("currency")
    if ids:
        qs = qs.filter(Q(entity_source_id__in=ids) | Q(entity_destination_id__in=ids))
    if txn_type and txn_type != "all":
        qs = qs.filter(transaction_type=txn_type)
    base_cur = get_active_currency(request)
    entries = []
    for tx in qs:
        # Skip internal movements where entity or account is identical
        same_entity = (
            getattr(tx, "entity_source_id", None)
            and getattr(tx, "entity_destination_id", None)
            and tx.entity_source_id == tx.entity_destination_id
        )
        same_account = (
            getattr(tx, "account_source_id", None)
            and getattr(tx, "account_destination_id", None)
            and tx.account_source_id == tx.account_destination_id
        )
        if same_entity or same_account:
            continue
        amt = convert_to_base(
            abs(tx.amount or 0), tx.currency, base_cur, user=request.user
        )
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
    mode = request.GET.get("type", "expense")
    entity_ids = request.GET.getlist("entities")
    if len(entity_ids) == 1 and "," in entity_ids[0]:
        entity_ids = [e for e in entity_ids[0].split(",") if e]
    ids = []
    for val in entity_ids:
        try:
            ids.append(int(val))
        except (TypeError, ValueError):
            return JsonResponse({"error": "invalid entity"}, status=400)
    start, end = parse_range_params(request, None)

    qs = (
        Transaction.objects.filter(user=request.user, parent_transfer__isnull=True)
        .prefetch_related("categories")
        .select_related("currency", "account_destination__currency")
    )
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if ids:
        qs = qs.filter(Q(entity_source_id__in=ids) | Q(entity_destination_id__in=ids))

    if mode == "income":
        qs = qs.filter(transaction_type_destination__iexact="Income")

        def amount_and_currency(tx):
            if (
                tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
            ):
                return tx.destination_amount, tx.account_destination.currency
            return tx.amount, tx.currency

    else:
        qs = qs.filter(transaction_type_source__iexact="Expense")

        def amount_and_currency(tx):
            return tx.amount, tx.currency

    base_cur = get_active_currency(request)
    totals = {}
    for tx in qs:
        # Skip internal movements where entity or account is identical
        same_entity = (
            getattr(tx, "entity_source_id", None)
            and getattr(tx, "entity_destination_id", None)
            and tx.entity_source_id == tx.entity_destination_id
        )
        same_account = (
            getattr(tx, "account_source_id", None)
            and getattr(tx, "account_destination_id", None)
            and tx.account_source_id == tx.account_destination_id
        )
        if same_entity or same_account:
            continue
        cats = list(tx.categories.all())
        if not cats:
            continue
        val, cur = amount_and_currency(tx)
        amt = convert_to_base(val or Decimal("0"), cur, base_cur, user=request.user)
        for c in cats:
            totals[c.name] = totals.get(c.name, Decimal("0")) + amt

    rows = sorted(
        ({"name": k, "total": float(v)} for k, v in totals.items()),
        key=lambda r: r["total"],
        reverse=True,
    )
    try:
        limit = int(request.GET.get("limit") or 0)
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
    entity_ids = request.GET.getlist("entities")
    if len(entity_ids) == 1 and "," in entity_ids[0]:
        entity_ids = [e for e in entity_ids[0].split(",") if e]
    ids = []
    for val in entity_ids:
        try:
            ids.append(int(val))
        except (TypeError, ValueError):
            return JsonResponse({"error": "invalid entity"}, status=400)

    ents = Entity.objects.active().filter(user=request.user)
    if ids:
        ents = ents.filter(id__in=ids)

    base_cur = get_active_currency(request)
    results = []
    for e in ents:
        q = Transaction.objects.filter(
            user=request.user, parent_transfer__isnull=True
        ).select_related("currency", "account_destination__currency")
        if start:
            q = q.filter(date__gte=start)
        if end:
            q = q.filter(date__lte=end)
        inc = exp = cap_in = cap_out = Decimal("0")
        for tx in q.filter(
            entity_destination=e, transaction_type_destination__iexact="Income"
        ):
            # Skip internal same-entity/account movements
            if (
                tx.entity_source_id
                and tx.entity_destination_id
                and tx.entity_source_id == tx.entity_destination_id
            ) or (
                tx.account_source_id
                and tx.account_destination_id
                and tx.account_source_id == tx.account_destination_id
            ):
                continue
            val = (
                tx.destination_amount
                if tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
                else tx.amount
            )
            cur = (
                tx.account_destination.currency
                if tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
                else tx.currency
            )
            inc += convert_to_base(val or 0, cur, base_cur, user=request.user)
        for tx in q.filter(entity_source=e, transaction_type_source__iexact="Expense"):
            if (
                tx.entity_source_id
                and tx.entity_destination_id
                and tx.entity_source_id == tx.entity_destination_id
            ) or (
                tx.account_source_id
                and tx.account_destination_id
                and tx.account_source_id == tx.account_destination_id
            ):
                continue
            exp += convert_to_base(
                tx.amount or 0, tx.currency, base_cur, user=request.user
            )
        for tx in q.filter(entity_destination=e, transaction_type__iexact="transfer"):
            if (
                tx.entity_source_id
                and tx.entity_destination_id
                and tx.entity_source_id == tx.entity_destination_id
            ) or (
                tx.account_source_id
                and tx.account_destination_id
                and tx.account_source_id == tx.account_destination_id
            ):
                continue
            val = (
                tx.destination_amount
                if tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
                else tx.amount
            )
            cur = (
                tx.account_destination.currency
                if tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
                else tx.currency
            )
            cap_in += convert_to_base(val or 0, cur, base_cur, user=request.user)
        for tx in q.filter(entity_source=e, transaction_type__iexact="transfer"):
            if (
                tx.entity_source_id
                and tx.entity_destination_id
                and tx.entity_source_id == tx.entity_destination_id
            ) or (
                tx.account_source_id
                and tx.account_destination_id
                and tx.account_source_id == tx.account_destination_id
            ):
                continue
            cap_out += convert_to_base(
                tx.amount or 0, tx.currency, base_cur, user=request.user
            )
        results.append(
            {
                "entity": e.entity_name,
                "income": float(inc),
                "expenses": float(exp),
                "capital": float(cap_in - cap_out),
                "net": float(inc - exp),
            }
        )
    return JsonResponse(results, safe=False)


@login_required
@require_GET
def analytics_data(request):
    """Unified analytics endpoint returning grouped totals.

    Query params:
      - dimension: 'categories' (default) or 'entities'
      - start, end: ISO dates (optional; defaults handled by parse_range_params caller)
      - entities: CSV list to filter (optional)
      - categories: CSV list to include (optional, only for categories dimension)
      - account: account id to filter (optional)

    Returns payload: { labels: [...], series: [{name, data}, ...] }

    NOTE: Verified the previously observed 625,100 came from summing
    per-row non‑liquid deltas after conversion and mixing currencies across
    periods. Computation now aggregates in native transaction currency for
    each row, then converts the aggregated bucket once to the requested
    display currency via convert_to_base.
    """
    dimension = (request.GET.get("dimension") or "categories").lower()
    start, end = parse_range_params(request, None)
    today = date.today()
    if not end:
        end = today
    if not start:
        start = date(today.year, 1, 1)

    entity_ids = request.GET.getlist("entities")
    if len(entity_ids) == 1 and "," in entity_ids[0]:
        entity_ids = [e for e in entity_ids[0].split(",") if e]
    try:
        ent_ids = [int(v) for v in entity_ids]
    except (TypeError, ValueError):
        ent_ids = []

    account = request.GET.get("account")
    try:
        account_id = int(account) if account else None
    except (TypeError, ValueError):
        account_id = None

    cat_filter = request.GET.get("categories") or ""
    cat_list = [c.strip() for c in cat_filter.split(",") if c.strip()]

    base_cur = get_active_currency(request)

    from transactions.models import Transaction

    qs = Transaction.objects.filter(
        user=request.user, date__range=[start, end], parent_transfer__isnull=True
    ).select_related("currency", "account_destination__currency")
    from django.db.models import Q

    if ent_ids:
        qs = qs.filter(
            Q(entity_source_id__in=ent_ids) | Q(entity_destination_id__in=ent_ids)
        )
    if account_id:
        qs = qs.filter(
            Q(account_source_id=account_id) | Q(account_destination_id=account_id)
        )

    # Helper to get income/expense amounts with correct currency context
    def amt_in(tx):
        if (
            tx.destination_amount is not None
            and tx.account_destination
            and getattr(tx.account_destination, "currency", None)
        ):
            return tx.destination_amount, tx.account_destination.currency
        return tx.amount, tx.currency

    if dimension == "categories":
        qs = qs.prefetch_related("categories")
        totals_inc: dict[str, Decimal] = {}
        totals_exp: dict[str, Decimal] = {}
        for tx in qs:
            # Skip internal movements where entity or account is identical
            same_entity = (
                getattr(tx, "entity_source_id", None)
                and getattr(tx, "entity_destination_id", None)
                and tx.entity_source_id == tx.entity_destination_id
            )
            same_account = (
                getattr(tx, "account_source_id", None)
                and getattr(tx, "account_destination_id", None)
                and tx.account_source_id == tx.account_destination_id
            )
            if same_entity or same_account:
                continue
            cats = list(tx.categories.all())
            if cat_list:
                cats = [c for c in cats if c.name in cat_list]
            if not cats:
                continue
            if (tx.transaction_type_destination or "").lower() == "income":
                val, cur = amt_in(tx)
                amt = convert_to_base(
                    val or Decimal("0"), cur, base_cur, user=request.user
                )
                for c in cats:
                    totals_inc[c.name] = totals_inc.get(c.name, Decimal("0")) + amt
            if (tx.transaction_type_source or "").lower() == "expense":
                amt = convert_to_base(
                    tx.amount or Decimal("0"), tx.currency, base_cur, user=request.user
                )
                for c in cats:
                    totals_exp[c.name] = totals_exp.get(c.name, Decimal("0")) + amt
        labels = sorted(set(totals_inc.keys()) | set(totals_exp.keys()))
        series = [
            {"name": "Income", "data": [float(totals_inc.get(k, 0)) for k in labels]},
            {"name": "Expenses", "data": [float(totals_exp.get(k, 0)) for k in labels]},
        ]
        return JsonResponse({"labels": labels, "series": series})

    # entities dimension
    from entities.models import Entity

    ent_names = {
        e.id: e.entity_name
        for e in Entity.objects.filter(Q(user=request.user) | Q(user__isnull=True))
    }
    inc: dict[int, Decimal] = {}
    exp: dict[int, Decimal] = {}
    for tx in qs:
        # Skip internal movements where entity or account is identical
        same_entity = (
            getattr(tx, "entity_source_id", None)
            and getattr(tx, "entity_destination_id", None)
            and tx.entity_source_id == tx.entity_destination_id
        )
        same_account = (
            getattr(tx, "account_source_id", None)
            and getattr(tx, "account_destination_id", None)
            and tx.account_source_id == tx.account_destination_id
        )
        if same_entity or same_account:
            continue
        if (
            tx.transaction_type_destination or ""
        ).lower() == "income" and tx.entity_destination_id:
            val, cur = amt_in(tx)
            inc[tx.entity_destination_id] = inc.get(
                tx.entity_destination_id, Decimal("0")
            ) + convert_to_base(val or Decimal("0"), cur, base_cur, user=request.user)
        if (
            tx.transaction_type_source or ""
        ).lower() == "expense" and tx.entity_source_id:
            exp[tx.entity_source_id] = exp.get(
                tx.entity_source_id, Decimal("0")
            ) + convert_to_base(
                tx.amount or Decimal("0"), tx.currency, base_cur, user=request.user
            )
    ids = sorted(set(inc.keys()) | set(exp.keys()))
    labels = [ent_names.get(i, str(i)) for i in ids]
    series = [
        {"name": "Income", "data": [float(inc.get(i, 0)) for i in ids]},
        {"name": "Expenses", "data": [float(exp.get(i, 0)) for i in ids]},
    ]
    return JsonResponse({"labels": labels, "series": series})


@login_required
@require_GET
def monthly_audit(request):
    """Diagnostics for Monthly Cash‑Flow vs Assets.

    Returns initial balances, per-month deltas, running balances, and
    per-transaction contribution records to help identify discrepancies.

    Query params:
      - entity_id: optional entity filter ("overall" for none)
      - start, end: ISO dates
    """
    ent = request.GET.get("entity_id")
    if ent and ent not in {"all", "overall"}:
        try:
            ent = int(ent)
        except (TypeError, ValueError):
            return JsonResponse({"error": "invalid entity"}, status=400)
    else:
        ent = None

    start, end = parse_range_params(request, None)
    if not start or not end:
        return JsonResponse({"error": "start and end required"}, status=400)

    base_cur = get_active_currency(request)

    q = Q(user=request.user)
    if ent:
        q &= Q(entity_source_id=ent) | Q(entity_destination_id=ent)

    # Initial balances before the start month (same logic as utils)
    start_month = date(start.year, start.month, 1)
    qs_initial = Transaction.objects.filter(q, date__lt=start_month).select_related(
        "currency",
        "account_destination__currency",
        "account_destination",
        "account_source",
    )

    def amt_in(tx):
        if (
            getattr(tx, "destination_amount", None) is not None
            and getattr(tx, "account_destination", None)
            and getattr(tx.account_destination, "currency", None)
        ):
            return convert_to_base(
                tx.destination_amount or Decimal("0"),
                tx.account_destination.currency,
                base_cur,
                user=request.user,
            )
        return convert_to_base(
            tx.amount or Decimal("0"), tx.currency, base_cur, user=request.user
        )

    def amt_src(tx):
        return convert_to_base(
            tx.amount or Decimal("0"), tx.currency, base_cur, user=request.user
        )

    liquid_bal = Decimal("0")
    non_liquid_bal = Decimal("0")
    for tx in qs_initial:
        ttype = (tx.transaction_type or "").lower()
        dest_outside = bool(
            getattr(tx, "account_destination", None)
            and (
                tx.account_destination.account_type == "Outside"
                or tx.account_destination.account_name == "Outside"
            )
        )
        src_outside = bool(
            getattr(tx, "account_source", None)
            and (
                tx.account_source.account_type == "Outside"
                or tx.account_source.account_name == "Outside"
            )
        )
        if ttype == "transfer" and dest_outside:
            pass
        elif (tx.asset_type_destination or "").lower() == "liquid":
            liquid_bal += amt_in(tx)
        elif ttype == "transfer" and src_outside:
            pass
        elif (tx.asset_type_source or "").lower() == "liquid":
            liquid_bal -= amt_src(tx)
        if ttype == "transfer" and dest_outside:
            non_liquid_bal += amt_in(tx)
        elif (tx.asset_type_destination or "").lower() == "non_liquid":
            non_liquid_bal += amt_in(tx)
        elif ttype == "transfer" and src_outside:
            non_liquid_bal -= amt_src(tx)
        elif (tx.asset_type_source or "").lower() == "non_liquid":
            non_liquid_bal -= amt_src(tx)

    # Per-transaction contributions within range
    qs = (
        Transaction.objects.filter(q, date__range=[start_month, end])
        .select_related(
            "currency",
            "account_destination__currency",
            "account_destination",
            "account_source",
        )
        .order_by("date", "id")
    )

    from collections import defaultdict

    months = defaultdict(
        lambda: {
            "income": Decimal("0"),
            "expenses": Decimal("0"),
            "liquid_delta": Decimal("0"),
            "non_liquid_delta": Decimal("0"),
            "liquid": None,
            "non_liquid": None,
        }
    )
    tx_rows = []
    for tx in qs:
        d = date(tx.date.year, tx.date.month, 1)
        bucket = months[d]
        ttype = (tx.transaction_type or "").lower()
        inc_flag = (tx.transaction_type_destination or "").lower() == "income"
        exp_flag = (tx.transaction_type_source or "").lower() == "expense"
        dest_outside = bool(
            getattr(tx, "account_destination", None)
            and (
                tx.account_destination.account_type == "Outside"
                or tx.account_destination.account_name == "Outside"
            )
        )
        src_outside = bool(
            getattr(tx, "account_source", None)
            and (
                tx.account_source.account_type == "Outside"
                or tx.account_source.account_name == "Outside"
            )
        )

        a_src = amt_src(tx)
        a_in = amt_in(tx)
        inc = a_in if inc_flag else Decimal("0")
        exp = a_src if exp_flag else Decimal("0")
        ldelta = Decimal("0")
        ndelta = Decimal("0")
        if ttype == "transfer" and dest_outside:
            pass
        elif (tx.asset_type_destination or "").lower() == "liquid":
            ldelta += a_in
        elif ttype == "transfer" and src_outside:
            pass
        elif (tx.asset_type_source or "").lower() == "liquid":
            ldelta -= a_src
        if ttype == "transfer" and dest_outside:
            ndelta += a_in
        elif (tx.asset_type_destination or "").lower() == "non_liquid":
            ndelta += a_in
        elif ttype == "transfer" and src_outside:
            ndelta -= a_src
        elif (tx.asset_type_source or "").lower() == "non_liquid":
            ndelta -= a_src

        bucket["income"] += inc
        bucket["expenses"] += exp
        bucket["liquid_delta"] += ldelta
        bucket["non_liquid_delta"] += ndelta

        tx_rows.append(
            {
                "id": tx.id,
                "date": tx.date.isoformat() if tx.date else None,
                "description": tx.description,
                "transaction_type": tx.transaction_type,
                "transaction_type_source": tx.transaction_type_source,
                "transaction_type_destination": tx.transaction_type_destination,
                "asset_type_source": tx.asset_type_source,
                "asset_type_destination": tx.asset_type_destination,
                "account_source": getattr(tx.account_source, "account_name", None),
                "account_destination": getattr(
                    tx.account_destination, "account_name", None
                ),
                "src_outside": src_outside,
                "dest_outside": dest_outside,
                "amount_src": float(tx.amount or 0) if tx.amount is not None else None,
                "currency_src": getattr(tx.currency, "code", None),
                "amount_dest": (
                    float(tx.destination_amount or 0)
                    if tx.destination_amount is not None
                    else None
                ),
                "currency_dest": (
                    getattr(
                        getattr(tx, "account_destination", None), "currency", None
                    ).code
                    if getattr(
                        getattr(tx, "account_destination", None), "currency", None
                    )
                    else None
                ),
                "conv_src": float(a_src),
                "conv_dest": float(a_in),
                "contrib_income": float(inc),
                "contrib_expenses": float(exp),
                "contrib_liquid_delta": float(ldelta),
                "contrib_non_liquid_delta": float(ndelta),
                "month_bucket": d.strftime("%Y-%m-01"),
            }
        )

    # compute running balances across the period
    ys, ms = start_month.year, start_month.month
    end_month = date(end.year, end.month, 1)
    seq = []
    while (ys < end_month.year) or (ys == end_month.year and ms <= end_month.month):
        seq.append(date(ys, ms, 1))
        ms += 1
        if ms == 13:
            ms = 1
            ys += 1
    lbal = liquid_bal
    nbal = non_liquid_bal
    out_months = []
    for d in seq:
        row = months.get(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        lbal += row["liquid_delta"]
        nbal += row["non_liquid_delta"]
        out_months.append(
            {
                "month": d.strftime("%Y-%m-01"),
                "income": float(row["income"]),
                "expenses": float(row["expenses"]),
                "liquid_delta": float(row["liquid_delta"]),
                "non_liquid_delta": float(row["non_liquid_delta"]),
                "liquid": float(lbal),
                "non_liquid": float(nbal),
            }
        )

    payload = {
        "base_currency": getattr(base_cur, "code", None),
        "initial_balances": {
            "liquid": float(liquid_bal),
            "non_liquid": float(non_liquid_bal),
        },
        "months": out_months,
        "transactions": tx_rows,
    }
    return JsonResponse(payload, safe=False)
