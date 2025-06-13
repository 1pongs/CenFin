from django.shortcuts import render
from django.views.generic import TemplateView
from django.db.models import (
    Sum,
    Case,
    When,
    F,
    DecimalField,
    Value,
    CharField,
)
from django.db.models.functions import TruncMonth, Abs
from django.utils import timezone
from datetime import date
from transactions.models import Transaction

# Create your views here.

class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # aggregate money-in / money-out / net worth
        aggregates = Transaction.objects.aggregate(
            income=Sum(
                Case(When(transaction_type_destination="Income",
                          then=F("amount")),
                     default=0,
                     output_field=DecimalField())
            ),
            expenses=Sum(
                Case(When(transaction_type_source="Expense",
                          then=F("amount")),
                     default=0,
                     output_field=DecimalField())
            ),
            liquid=Sum(
                Case(When(asset_type_destination="Liquid", then=F("amount")),
                     When(asset_type_source="Liquid", then=-F("amount")),
                     default=0,
                     output_field=DecimalField())
            ),
            asset=Sum(
                Case(When(asset_type_destination="Non-Liquid", then=F("amount")),
                     When(asset_type_source="Non-Liquid", then=-F("amount")),
                     default=0,
                     output_field=DecimalField())
            ),
        )
        aggregates["net"] = (
            aggregates["income"] - aggregates["expenses"] + aggregates["liquid"] + aggregates["asset"]
        )

        ctx["totals"] = aggregates

        ctx["cards"] = [
            ("Income",    "income",    "success"),
            ("Expenses",  "expenses",  "danger"),
            ("Liquid", "liquid", "warning"),
            ("Asset", "asset", "info"),
            ("Net Worth", "net",       "primary"),
        ]

        # ------------------------------------------------------
        # Monthly cash-flow summary (rolling 12 months)
        # ------------------------------------------------------
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

        initial = Transaction.objects.filter(date__lt=start_date).aggregate(
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
            Transaction.objects.filter(date__gte=start_date)
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
            month_val = row["month"]
            if hasattr(month_val, "date"):
                month_val = month_val.date()
            month_map[month_val] = row

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
            income = row.get("income", 0) or 0
            expenses = row.get("expenses", 0) or 0
            liquid_bal += row.get("liquid_delta", 0) or 0
            non_liquid_bal += row.get("non_liquid_delta", 0) or 0
            summary.append({
                "month": d.strftime("%b"),
                "income": income,
                "expenses": expenses,
                "liquid": liquid_bal,
                "non_liquid": non_liquid_bal,
            })
        ctx["monthly_summary"] = summary

        # ------------------------------------------------------
        # Top 10 big-ticket transactions for the current year
        # ------------------------------------------------------
        year_start = date(today.year, 1, 1)
        top_entries_qs = (
            Transaction.objects.filter(date__gte=year_start)
            .annotate(abs_amount=Abs("amount"))
            .annotate(
                entry_type=Case(
                    When(transaction_type_destination="Income", then=Value("income")),
                    When(transaction_type_source="Expense", then=Value("expense")),
                    When(asset_type_destination="Non-Liquid", then=Value("non_liquid")),
                    default=Value("other"),
                    output_field=CharField(),
                )
            )
            .order_by("-abs_amount")[:10]
            .values("description", "abs_amount", "entry_type")
        )
        ctx["top10_entries"] = [
            {"description": row["description"], "amount": row["abs_amount"], "type": row["entry_type"]}
            for row in top_entries_qs
        ]

        return ctx