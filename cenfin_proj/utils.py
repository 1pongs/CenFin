from decimal import Decimal
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (Sum, F, Value, DecimalField, Case, When, Q)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity
from utils.currency import convert_to_base
from utils.currency import convert_amount


def get_account_balances():
    """Return active accounts annotated with their current balance."""
    return Account.objects.active().with_current_balance().order_by("account_name")


def get_entity_balances():
    """Return active entities annotated with their current balance."""
    return (
        Entity.objects.active()
        .annotate(
            inflow=Coalesce(
                Sum(
                    Case(
                        When(
                            transaction_entity_destination__destination_amount__isnull=False,
                            then=F("transaction_entity_destination__destination_amount"),
                        ),
                        default=F("transaction_entity_destination__amount"),
                        output_field=DecimalField(),
                    ),
                    filter=Q(
                        transaction_entity_destination__asset_type_destination__iexact="liquid"
                    ),
                ),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
            outflow=Coalesce(
                Sum(
                    "transaction_entity_source__amount",
                    filter=Q(
                        transaction_entity_source__asset_type_source__iexact="liquid"
                    ),
                ),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
        )
        .annotate(balance=F("inflow") - F("outflow"))
        .order_by("entity_name")
    )


def get_entity_liquid_nonliquid_totals(user, disp_code: str) -> dict[int, dict[str, Decimal]]:
    """Return per-entity liquid and non‑liquid net totals converted to ``disp_code``.

    Rules mirror entities.utils helpers:
    - Liquid: ignore transfers to/from Outside; add dest when asset_type_destination == 'liquid';
      subtract src when asset_type_source == 'liquid'.
    - Non‑liquid: treat transfers to Outside as inflow (capital in); from Outside as outflow (capital out);
      otherwise add dest when asset_type_destination == 'non_liquid'; subtract src when asset_type_source == 'non_liquid'.
    - Exclude hidden child legs (parent_transfer__isnull=True).
    - Skip internal movements where entity or account are identical (no net effect).
    """
    from collections import defaultdict
    from transactions.models import Transaction

    totals_liq: dict[int, Decimal] = defaultdict(Decimal)
    totals_non: dict[int, Decimal] = defaultdict(Decimal)

    txs = (
        Transaction.objects.filter(user=user, parent_transfer__isnull=True)
        .select_related("currency", "account_destination__currency", "account_source", "account_destination")
    )

    for tx in txs:
        # Skip if internal to the same entity or same account
        if (
            getattr(tx, "entity_source_id", None)
            and getattr(tx, "entity_destination_id", None)
            and tx.entity_source_id == tx.entity_destination_id
        ):
            continue
        if (
            getattr(tx, "account_source_id", None)
            and getattr(tx, "account_destination_id", None)
            and tx.account_source_id == tx.account_destination_id
        ):
            continue

        ttype = (getattr(tx, "transaction_type", "") or "").lower()
        dest_outside = bool(
            getattr(tx, "account_destination", None)
            and (
                getattr(tx.account_destination, "account_type", None) == "Outside"
                or getattr(tx.account_destination, "account_name", None) == "Outside"
            )
        )
        src_outside = bool(
            getattr(tx, "account_source", None)
            and (
                getattr(tx.account_source, "account_type", None) == "Outside"
                or getattr(tx.account_source, "account_name", None) == "Outside"
            )
        )

        # Destination-side amount/currency
        dest_amt = tx.destination_amount if tx.destination_amount is not None else tx.amount
        dest_code = (
            tx.account_destination.currency.code
            if tx.destination_amount is not None
            and tx.account_destination_id
            and tx.account_destination
            and tx.account_destination.currency
            else (tx.currency.code if tx.currency else None)
        )

        # Liquid inflow to entity (skip transfers to Outside)
        if (
            tx.entity_destination_id
            and not (ttype == "transfer" and dest_outside)
            and (getattr(tx, "asset_type_destination", "") or "").lower() == "liquid"
            and dest_amt is not None
            and dest_code is not None
        ):
            totals_liq[tx.entity_destination_id] += convert_amount(dest_amt, dest_code, disp_code)

        # Liquid outflow from entity (skip transfers from Outside)
        if (
            tx.entity_source_id
            and not (ttype == "transfer" and src_outside)
            and (getattr(tx, "asset_type_source", "") or "").lower() == "liquid"
            and tx.amount is not None
            and tx.currency is not None
        ):
            totals_liq[tx.entity_source_id] -= convert_amount(tx.amount, tx.currency.code, disp_code)

        # Non‑liquid inflow/outflow
        if tx.entity_destination_id and dest_amt is not None and dest_code is not None:
            if ttype == "transfer" and dest_outside:
                totals_non[tx.entity_destination_id] += convert_amount(dest_amt, dest_code, disp_code)
            elif (getattr(tx, "asset_type_destination", "") or "").lower() == "non_liquid":
                totals_non[tx.entity_destination_id] += convert_amount(dest_amt, dest_code, disp_code)

        if tx.entity_source_id and tx.amount is not None and tx.currency is not None:
            if ttype == "transfer" and src_outside:
                totals_non[tx.entity_source_id] -= convert_amount(tx.amount, tx.currency.code, disp_code)
            elif (getattr(tx, "asset_type_source", "") or "").lower() == "non_liquid":
                totals_non[tx.entity_source_id] -= convert_amount(tx.amount, tx.currency.code, disp_code)

    # Merge into a single dict per entity id
    out: dict[int, dict[str, Decimal]] = {}
    for ent_id in set(list(totals_liq.keys()) + list(totals_non.keys())):
        out[ent_id] = {
            "liquid": totals_liq.get(ent_id, Decimal("0")),
            "non_liquid": totals_non.get(ent_id, Decimal("0")),
        }
    return out


def get_entity_balance(entity_id, user=None):
    """Return balance for a single entity."""
    from transactions.models import Transaction
    qs = Transaction.all_objects.filter(child_transfers__isnull=True)
    if user is not None:
        qs = qs.filter(user=user)
    inflow = (
        qs.filter(
            entity_destination_id=entity_id,
            asset_type_destination__iexact="liquid",
        ).aggregate(
            total=Sum(
                Case(
                    When(destination_amount__isnull=False, then=F("destination_amount")),
                    default=F("amount"),
                    output_field=DecimalField(),
                )
            )
        )["total"]
        or Decimal("0")
    )
    outflow = (
        qs.filter(
            entity_source_id=entity_id,
            asset_type_source__iexact="liquid",
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    return inflow - outflow


def get_account_balance(account_id, user=None):
    """Return balance for a single account."""
    qs = Account.objects.filter(pk=account_id)
    if user is not None:
        qs = qs.filter(user=user)
    bal = (
        qs.with_current_balance()
        .values_list("current_balance", flat=True)
        .first()
    )
    return bal or Decimal("0")


def get_account_entity_balance(account_id, entity_id, user=None):
    """Return balance for an account/entity pair."""
    from transactions.models import Transaction
    qs = Transaction.all_objects.filter(child_transfers__isnull=True)
    if user is not None:
        qs = qs.filter(user=user)
    inflow = (
        qs.filter(
            account_destination_id=account_id,
            entity_destination_id=entity_id,
            asset_type_destination__iexact="liquid",
        ).aggregate(
            total=Sum(
                Case(
                    When(destination_amount__isnull=False, then=F("destination_amount")),
                    default=F("amount"),
                    output_field=DecimalField(),
                )
            )
        )["total"]
        or Decimal("0")
    )
    outflow = (
        qs.filter(
            account_source_id=account_id,
            entity_source_id=entity_id,
            asset_type_source__iexact="liquid",
        )
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    return inflow - outflow


def get_monthly_cash_flow(
    entity_id=None,
    months=12,
    drop_empty=False,
    user=None,
    currency=None,
):
    """Return rolling cash-flow data for the given months filtered by user.

    All amounts are converted to ``currency`` before aggregation.  When
    ``currency`` is ``None`` the raw transaction amounts are used.
    """
    
    from transactions.models import Transaction

    if months not in {3, 6, 12}:
        months = 12

    q = Q()
    if entity_id:
        q = Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id)
    if user is not None:
        q &= Q(user=user)
    if entity_id and not Transaction.objects.filter(q).exists():
        return []

    today = timezone.now().date()
    first = date(today.year, today.month, 1)
    y, m = first.year, first.month
    for _ in range(months - 1):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    start_date = date(y, m, 1)

    qs_initial = Transaction.objects.filter(q, date__lt=start_date).select_related(
        "currency",
        "account_destination__currency",
        "account_destination",
        "account_source",
    )
    liquid_bal = Decimal("0")
    non_liquid_bal = Decimal("0")
    def amt_in(tx):
        if (
            getattr(tx, "destination_amount", None) is not None
            and getattr(tx, "account_destination", None)
            and getattr(tx.account_destination, "currency", None)
        ):
            return convert_to_base(tx.destination_amount or Decimal("0"), tx.account_destination.currency, currency, user=user)
        return convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)

    for tx in qs_initial:
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
        # Apply side-aware initial balance contributions when filtering by entity
        match_dest = entity_id is None or tx.entity_destination_id == entity_id
        match_src = entity_id is None or tx.entity_source_id == entity_id
        amt = convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)
        ttype = (tx.transaction_type or "").lower()
        dest_outside = bool(getattr(tx, "account_destination", None) and (tx.account_destination.account_type == "Outside" or tx.account_destination.account_name == "Outside"))
        src_outside = bool(getattr(tx, "account_source", None) and (tx.account_source.account_type == "Outside" or tx.account_source.account_name == "Outside"))
        if match_dest:
            if not (ttype == "transfer" and dest_outside) and (tx.asset_type_destination or "").lower() == "liquid":
                liquid_bal += amt_in(tx)
        if match_src:
            if not (ttype == "transfer" and src_outside) and (tx.asset_type_source or "").lower() == "liquid":
                liquid_bal -= amt
        if match_dest:
            if ttype == "transfer" and dest_outside:
                non_liquid_bal += amt_in(tx)
            elif (tx.asset_type_destination or "").lower() == "non_liquid":
                non_liquid_bal += amt_in(tx)
        if match_src:
            if ttype == "transfer" and src_outside:
                non_liquid_bal -= amt
            elif (tx.asset_type_source or "").lower() == "non_liquid":
                non_liquid_bal -= amt

    month_map: dict[date, dict] = {}
    qs = (
        Transaction.objects.filter(q, date__gte=start_date)
        .select_related("currency", "account_destination__currency", "account_destination", "account_source")
        .order_by("date")
    )
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
        match_dest = entity_id is None or tx.entity_destination_id == entity_id
        match_src = entity_id is None or tx.entity_source_id == entity_id
        d = date(tx.date.year, tx.date.month, 1)
        row = month_map.setdefault(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        amt_src = convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)
        amt_dest = amt_in(tx)
        if match_dest and (tx.transaction_type_destination or "").lower() == "income":
            row["income"] += amt_dest
        if match_src and (tx.transaction_type_source or "").lower() == "expense":
            row["expenses"] += amt_src
        ttype = (tx.transaction_type or "").lower()
        dest_outside = bool(getattr(tx, "account_destination", None) and (tx.account_destination.account_type == "Outside" or tx.account_destination.account_name == "Outside"))
        src_outside = bool(getattr(tx, "account_source", None) and (tx.account_source.account_type == "Outside" or tx.account_source.account_name == "Outside"))
        if match_dest:
            if not (ttype == "transfer" and dest_outside) and (tx.asset_type_destination or "").lower() == "liquid":
                row["liquid_delta"] += amt_dest
            if ttype == "transfer" and dest_outside:
                row["non_liquid_delta"] += amt_dest
            elif (tx.asset_type_destination or "").lower() == "non_liquid":
                row["non_liquid_delta"] += amt_dest
        if match_src:
            if not (ttype == "transfer" and src_outside) and (tx.asset_type_source or "").lower() == "liquid":
                row["liquid_delta"] -= amt_src
            if ttype == "transfer" and src_outside:
                row["non_liquid_delta"] -= amt_src
            elif (tx.asset_type_source or "").lower() == "non_liquid":
                row["non_liquid_delta"] -= amt_src

    months_seq = []
    y = start_date.year
    m = start_date.month
    for _ in range(months):
        months_seq.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1

    summary = []
    for d in months_seq:
        row = month_map.get(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        liquid_bal += row["liquid_delta"]
        non_liquid_bal += row["non_liquid_delta"]
        item = {
            "month": d.strftime("%b"),
            "income": row["income"],
            "expenses": row["expenses"],
            "liquid": liquid_bal,
            "non_liquid": non_liquid_bal,
        }
        if (
            drop_empty
            and item["income"] == 0
            and item["expenses"] == 0
            and row["liquid_delta"] == 0
            and row["non_liquid_delta"] == 0
        ):
            continue
        summary.append(item)
    return summary


def get_monthly_summary(entity_id=None, user=None, currency=None):
    """Return rolling 12 month cash-flow summary.

    All values are converted to ``currency`` before aggregation.  When
    ``currency`` is ``None`` the original amounts are used.
    """

    from django.db.models import Q
    from django.utils import timezone
    from datetime import date
    from transactions.models import Transaction

    today = timezone.now().date()
    first_this_month = date(today.year, today.month, 1)
    year = first_this_month.year
    month = first_this_month.month
    for _ in range(11):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    start_date = date(year, month, 1)

    q = Q()
    if entity_id:
        q = Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id)
    if user is not None:
        q &= Q(user=user)
    if entity_id and not Transaction.objects.filter(q).exists():
        return []

    qs_initial = Transaction.objects.filter(q, date__lt=start_date).select_related(
        "currency",
        "account_destination__currency",
        "account_destination",
        "account_source",
    )
    liquid_bal = Decimal("0")
    non_liquid_bal = Decimal("0")
    def _ms_amt_in(tx):
        if (
            getattr(tx, "destination_amount", None) is not None
            and getattr(tx, "account_destination", None)
            and getattr(tx.account_destination, "currency", None)
        ):
            return convert_to_base(tx.destination_amount or Decimal("0"), tx.account_destination.currency, currency, user=user)
        return convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)

    for tx in qs_initial:
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
        match_dest = entity_id is None or tx.entity_destination_id == entity_id
        match_src = entity_id is None or tx.entity_source_id == entity_id
        amt_src = convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)
        amt_dest = _ms_amt_in(tx)
        if match_dest and (tx.asset_type_destination or "").lower() == "liquid":
            liquid_bal += amt_dest
        if match_src and (tx.asset_type_source or "").lower() == "liquid":
            liquid_bal -= amt_src
        if match_dest and (tx.asset_type_destination or "").lower() == "non_liquid":
            non_liquid_bal += amt_dest
        if match_src and (tx.asset_type_source or "").lower() == "non_liquid":
            non_liquid_bal -= amt_src

    month_map: dict[date, dict] = {}
    qs = (
        Transaction.objects.filter(q, date__gte=start_date)
        .select_related("currency", "account_destination__currency", "account_destination", "account_source")
        .order_by("date")
    )
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
        match_dest = entity_id is None or tx.entity_destination_id == entity_id
        match_src = entity_id is None or tx.entity_source_id == entity_id
        d = date(tx.date.year, tx.date.month, 1)
        row = month_map.setdefault(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        amt_src = convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)
        amt_dest = _ms_amt_in(tx)
        if match_dest and (tx.transaction_type_destination or "").lower() == "income":
            row["income"] += amt_dest
        if match_src and (tx.transaction_type_source or "").lower() == "expense":
            row["expenses"] += amt_src
        if match_dest and (tx.asset_type_destination or "").lower() == "liquid":
            row["liquid_delta"] += amt_dest
        if match_src and (tx.asset_type_source or "").lower() == "liquid":
            row["liquid_delta"] -= amt_src
        if match_dest and (tx.asset_type_destination or "").lower() == "non_liquid":
            row["non_liquid_delta"] += amt_dest
        if match_src and (tx.asset_type_source or "").lower() == "non_liquid":
            row["non_liquid_delta"] -= amt_src

    months = []
    y = start_date.year
    m = start_date.month
    for _ in range(12):
        months.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1

    summary = []
    for d in months:
        row = month_map.get(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        liquid_bal += row["liquid_delta"]
        non_liquid_bal += row["non_liquid_delta"]
        summary.append(
            {
                "month": d.strftime("%b"),
                "income": row["income"],
                "expenses": row["expenses"],
                "liquid": liquid_bal,
                "non_liquid": non_liquid_bal,
            }
        )
    return summary


def parse_range_params(request, default_start, default_end=None):
    """Parse start/end date strings from request.GET with defaults."""
    today = timezone.now().date()
    if default_end is None:
        default_end = today
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    try:
        start = date.fromisoformat(start_str) if start_str else default_start
    except (TypeError, ValueError):
        start = default_start
    try:
        end = date.fromisoformat(end_str) if end_str else default_end
    except (TypeError, ValueError):
        end = default_end
    return start, end


def get_monthly_cash_flow_range(
    entity_id=None,
    start=None,
    end=None,
    drop_empty=False,
    user=None,
    currency=None,
):
    """Return monthly cash-flow data for the given date range."""

    from transactions.models import Transaction

    if start is None or end is None:
        raise ValueError("start and end dates are required")

    q = Q()
    if entity_id:
        q = Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id)
    if user is not None:
        q &= Q(user=user)
    if entity_id and not Transaction.objects.filter(q).exists():
        return []

    start_month = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)

    months_seq = []
    y, m = start_month.year, start_month.month
    while (y < end_month.year) or (y == end_month.year and m <= end_month.month):
        months_seq.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1

    qs_initial = Transaction.objects.filter(q, date__lt=start_month).select_related(
        "currency",
        "account_destination__currency",
        "account_destination",
        "account_source",
    )
    liquid_bal = Decimal("0")
    non_liquid_bal = Decimal("0")
    def _range_amt_in(tx):
        if (
            getattr(tx, "destination_amount", None) is not None
            and getattr(tx, "account_destination", None)
            and getattr(tx.account_destination, "currency", None)
        ):
            return convert_to_base(tx.destination_amount or Decimal("0"), tx.account_destination.currency, currency, user=user)
        return convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)

    for tx in qs_initial:
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
        match_dest = entity_id is None or tx.entity_destination_id == entity_id
        match_src = entity_id is None or tx.entity_source_id == entity_id
        amt = convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)
        ttype = (tx.transaction_type or "").lower()
        dest_outside = bool(getattr(tx, "account_destination", None) and (tx.account_destination.account_type == "Outside" or tx.account_destination.account_name == "Outside"))
        src_outside = bool(getattr(tx, "account_source", None) and (tx.account_source.account_type == "Outside" or tx.account_source.account_name == "Outside"))
        if match_dest:
            if not (ttype == "transfer" and dest_outside) and (tx.asset_type_destination or "").lower() == "liquid":
                liquid_bal += _range_amt_in(tx)
            if ttype == "transfer" and dest_outside:
                non_liquid_bal += _range_amt_in(tx)
            elif (tx.asset_type_destination or "").lower() == "non_liquid":
                non_liquid_bal += _range_amt_in(tx)
        if match_src:
            if not (ttype == "transfer" and src_outside) and (tx.asset_type_source or "").lower() == "liquid":
                liquid_bal -= amt
            if ttype == "transfer" and src_outside:
                non_liquid_bal -= amt
            elif (tx.asset_type_source or "").lower() == "non_liquid":
                non_liquid_bal -= amt

    month_map: dict[date, dict] = {}
    qs = (
        Transaction.objects.filter(q, date__range=[start_month, end])
        .select_related("currency", "account_destination__currency", "account_destination", "account_source")
        .order_by("date")
    )
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
        match_dest = entity_id is None or tx.entity_destination_id == entity_id
        match_src = entity_id is None or tx.entity_source_id == entity_id
        d = date(tx.date.year, tx.date.month, 1)
        row = month_map.setdefault(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        amt_src = convert_to_base(tx.amount or Decimal("0"), tx.currency, currency, user=user)
        amt_dest = _range_amt_in(tx)
        if match_dest and (tx.transaction_type_destination or "").lower() == "income":
            row["income"] += amt_dest
        if match_src and (tx.transaction_type_source or "").lower() == "expense":
            row["expenses"] += amt_src
        ttype = (tx.transaction_type or "").lower()
        dest_outside = bool(getattr(tx, "account_destination", None) and (tx.account_destination.account_type == "Outside" or tx.account_destination.account_name == "Outside"))
        src_outside = bool(getattr(tx, "account_source", None) and (tx.account_source.account_type == "Outside" or tx.account_source.account_name == "Outside"))
        if match_dest:
            if not (ttype == "transfer" and dest_outside) and (tx.asset_type_destination or "").lower() == "liquid":
                row["liquid_delta"] += amt_dest
            if ttype == "transfer" and dest_outside:
                row["non_liquid_delta"] += amt_dest
            elif (tx.asset_type_destination or "").lower() == "non_liquid":
                row["non_liquid_delta"] += amt_dest
        if match_src:
            if not (ttype == "transfer" and src_outside) and (tx.asset_type_source or "").lower() == "liquid":
                row["liquid_delta"] -= amt_src
            if ttype == "transfer" and src_outside:
                row["non_liquid_delta"] -= amt_src
            elif (tx.asset_type_source or "").lower() == "non_liquid":
                row["non_liquid_delta"] -= amt_src

    summary = []
    for d in months_seq:
        row = month_map.get(
            d,
            {
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "liquid_delta": Decimal("0"),
                "non_liquid_delta": Decimal("0"),
            },
        )
        liquid_bal += row["liquid_delta"]
        non_liquid_bal += row["non_liquid_delta"]
        item = {
            "month": d.strftime("%b"),
            "income": row["income"],
            "expenses": row["expenses"],
            "liquid": liquid_bal,
            "non_liquid": non_liquid_bal,
        }
        if (
            drop_empty
            and item["income"] == 0
            and item["expenses"] == 0
            and row["liquid_delta"] == 0
            and row["non_liquid_delta"] == 0
        ):
            continue
        summary.append(item)
    return summary
