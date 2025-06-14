from django.shortcuts import render
from django.views.generic import TemplateView, View
from django.db.models import (
    Sum,
    Case,
    When,
    F,
    DecimalField,
    Value,
    CharField,
)
from django.db.models.functions import Abs
from django.utils import timezone
from datetime import date

from django.http import JsonResponse
from transactions.models import Transaction
from entities.models import Entity
from cenfin_proj.utils import get_monthly_summary, get_monthly_cash_flow

# Create your views here.

class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # aggregate money-in / money-out / net worth
        aggregates = Transaction.objects.filter(user=self.request.user).aggregate(
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
        income = aggregates.get("income") or 0
        expenses = aggregates.get("expenses") or 0
        liquid = aggregates.get("liquid") or 0
        asset = aggregates.get("asset") or 0
        aggregates["income"] = income
        aggregates["expenses"] = expenses
        aggregates["liquid"] = liquid
        aggregates["asset"] = asset
        aggregates["net"] = income - expenses + asset

        ctx["totals"] = aggregates

        ctx["cards"] = [
            ("Income",    "income",    "success"),
            ("Expenses",  "expenses",  "danger"),
            ("Liquid", "liquid", "warning"),
            ("Asset", "asset", "info"),
            ("Net Worth", "net",       "primary"),
        ]
        ctx["monthly_summary"] = get_monthly_summary(user=self.request.user)
        today = timezone.now().date()
        
        ctx["entities"] = Entity.objects.active().filter(user=self.request.user).order_by("entity_name")
        # ------------------------------------------------------
        # Top 10 big-ticket transactions for the current year
        # ------------------------------------------------------
        year_start = date(today.year, 1, 1)
        top_entries_qs = (
            Transaction.objects.filter(user=self.request.user, date__gte=year_start)
            .annotate(abs_amount=Abs("amount"))
            .annotate(
                entry_type=Case(
                    When(transaction_type_destination="Income", then=Value("income")),
                    When(transaction_type_source="Expense", then=Value("expense")),
                    When(asset_type_destination="Non-Liquid", then=Value("asset")),
                    default=Value("other"),
                    output_field=CharField(),
                )
            )
            .order_by("-abs_amount")[:10]
            .values("description", "abs_amount", "entry_type")
            .values(category=F("description"), amount=F("abs_amount"), type=F("entry_type"))
        )
        ctx["top10_big_tickets"] = list(top_entries_qs)

        return ctx

class MonthlyDataView(View):
    """Return monthly summary JSON filtered by entity."""
    def get(self, request, *args, **kwargs):
        ent = request.GET.get("entity_id")
        if ent and ent != "all":
            try:
                ent = int(ent)
            except (TypeError, ValueError):
                return JsonResponse({"error": "invalid entity"}, status=400)
        else:
            ent = None
        data = get_monthly_summary(ent, user=request.user)
        return JsonResponse(data, safe=False)
    

class MonthlyChartDataView(View):
    """Return monthly chart data filtered by entity and months."""

    def get(self, request, *args, **kwargs):
        ent = request.GET.get("entity")
        months = request.GET.get("months")
        if ent and ent != "all":
            try:
                ent = int(ent)
            except (TypeError, ValueError):
                return JsonResponse({"error": "invalid entity"}, status=400)
        else:
            ent = None

        try:
            months = int(months)
        except (TypeError, ValueError):
            months = 12

        data = get_monthly_cash_flow(ent, months, drop_empty=True, user=request.user)
        return JsonResponse(data, safe=False)
    