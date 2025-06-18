from decimal import Decimal
from datetime import date

from django.db.models import (Sum, F, Value, DecimalField, Case, When, Q)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from accounts.models import Account
from entities.models import Entity


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
                    "transaction_entity_destination__amount",
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


def get_entity_balance(entity_id, user=None):
    """Return balance for a single entity."""
    from transactions.models import Transaction
    qs = Transaction.objects
    if user is not None:
        qs = qs.filter(user=user)
    inflow = (
        qs.filter(
            entity_destination_id=entity_id,
            asset_type_destination__iexact="liquid",
        )
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    outflow = (
        qs.filter(
            entity_source_id=entity_id,
            asset_type_source__iexact="liquid",
        )
        .aggregate(total=Sum("amount"))["total"]
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
    qs = Transaction.objects
    if user is not None:
        qs = qs.filter(user=user)
    inflow = (
        qs.filter(
            account_destination_id=account_id,
            entity_destination_id=entity_id,
            asset_type_destination__iexact="liquid",
        )
        .aggregate(total=Sum("amount"))["total"]
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


def get_monthly_cash_flow(entity_id=None, months=12, drop_empty=False, user=None):
    """Return rolling cash-flow data for the given months filtered by user."""
    from transactions.models import Transaction
    if months not in {3, 6, 12}:
        months = 12

    q = Q()
    if entity_id:
        q = Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id)
    if user is not None:
        q &= Q(user=user)
    if entity_id:
        if not Transaction.objects.filter(q).exists():
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

    initial = Transaction.objects.filter(q, date__lt=start_date).aggregate(
        liquid=Sum(
            Case(
                When(asset_type_destination="Liquid", then=F("amount")),
                When(asset_type_source="Liquid", then=-F("amount")),
                default=0,
                output_field=DecimalField(),
            )
        ),
        non_liquid=Sum(
            Case(
                When(asset_type_destination="Non-Liquid", then=F("amount")),
                When(asset_type_source="Non-Liquid", then=-F("amount")),
                default=0,
                output_field=DecimalField(),
            )
        ),
    )

    qs = (
        Transaction.objects.filter(q, date__gte=start_date)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            income=Sum(
                Case(
                    When(transaction_type_destination="Income", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            expenses=Sum(
                Case(
                    When(transaction_type_source="Expense", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            liquid_delta=Sum(
                Case(
                    When(asset_type_destination="Liquid", then=F("amount")),
                    When(asset_type_source="Liquid", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            non_liquid_delta=Sum(
                Case(
                    When(asset_type_destination="Non-Liquid", then=F("amount")),
                    When(asset_type_source="Non-Liquid", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
        )
        .order_by("month")
    )

    month_map = {}
    for row in qs:
        mv = row["month"].date() if hasattr(row["month"], "date") else row["month"]
        month_map[mv] = row

    months_seq = []
    y = start_date.year
    m = start_date.month
    for _ in range(months):
        months_seq.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1

    liquid_bal = initial.get("liquid") or 0
    non_liquid_bal = initial.get("non_liquid") or 0
    summary = []
    for d in months_seq:
        row = month_map.get(d, {})
        liquid_bal += row.get("liquid_delta", 0) or 0
        non_liquid_bal += row.get("non_liquid_delta", 0) or 0
        item = {
            "month": d.strftime("%b"),
            "income": row.get("income", 0) or 0,
            "expenses": row.get("expenses", 0) or 0,
            "liquid": liquid_bal,
            "non_liquid": non_liquid_bal,
        }
        if drop_empty and item["income"] == 0 and item["expenses"] == 0 and row.get("liquid_delta", 0) == 0 and row.get("non_liquid_delta", 0) == 0:
            continue
        summary.append(item)
    return summary


def get_monthly_summary(entity_id=None, user=None):
    """Return rolling 12 month cash-flow summary optionally filtered by entity and user."""
    from django.db.models import Q
    from django.db.models.functions import TruncMonth
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
    if entity_id:
        if not Transaction.objects.filter(q).exists():
            return []

    initial = Transaction.objects.filter(q, date__lt=start_date).aggregate(
        liquid=Sum(
            Case(
                When(asset_type_destination="Liquid", then=F("amount")),
                When(asset_type_source="Liquid", then=-F("amount")),
                default=0,
                output_field=DecimalField(),
            )
        ),
        non_liquid=Sum(
            Case(
                When(asset_type_destination="Non-Liquid", then=F("amount")),
                When(asset_type_source="Non-Liquid", then=-F("amount")),
                default=0,
                output_field=DecimalField(),
            )
        ),
    )

    qs = (
        Transaction.objects.filter(q, date__gte=start_date)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            income=Sum(
                Case(
                    When(transaction_type_destination="Income", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            expenses=Sum(
                Case(
                    When(transaction_type_source="Expense", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            liquid_delta=Sum(
                Case(
                    When(asset_type_destination="Liquid", then=F("amount")),
                    When(asset_type_source="Liquid", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            non_liquid_delta=Sum(
                Case(
                    When(asset_type_destination="Non-Liquid", then=F("amount")),
                    When(asset_type_source="Non-Liquid", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
        )
        .order_by("month")
    )

    month_map = {}
    for row in qs:
        mv = row["month"].date() if hasattr(row["month"], "date") else row["month"]
        month_map[mv] = row

    months = []
    y = start_date.year
    m = start_date.month
    for _ in range(12):
        months.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1

    liquid_bal = initial.get("liquid") or 0
    non_liquid_bal = initial.get("non_liquid") or 0
    summary = []
    for d in months:
        row = month_map.get(d, {})
        liquid_bal += row.get("liquid_delta", 0) or 0
        non_liquid_bal += row.get("non_liquid_delta", 0) or 0
        summary.append(
            {
                "month": d.strftime("%b"),
                "income": row.get("income", 0) or 0,
                "expenses": row.get("expenses", 0) or 0,
                "liquid": liquid_bal,
                "non_liquid": non_liquid_bal,
            }
        )
    return summary