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
    Q,
)
from django.db.models.functions import Abs
from django.utils import timezone
from datetime import date, timedelta

from django.http import JsonResponse
from transactions.models import Transaction
from transactions.constants import TXN_TYPE_CHOICES
from entities.models import Entity
from cenfin_proj.utils import (
    get_monthly_summary,
    get_monthly_cash_flow,
    parse_range_params,
)

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
        ctx["today"] = today
        
        ctx["entities"] = Entity.objects.active().filter(user=self.request.user).order_by("entity_name")
        params = self.request.GET
        start_cf, end_cf = parse_range_params(self.request, today - timedelta(days=365))
        start_top, end_top = parse_range_params(self.request, date(today.year, 1, 1))
        ctx["range_start_cf"] = start_cf
        ctx["range_end_cf"] = end_cf
        ctx["range_start_top"] = start_top
        ctx["range_end_top"] = end_top
        selected_entities = []
        for val in params.getlist("entities"):
            if "," in val:
                selected_entities.extend([e for e in val.split(",") if e])
            else:
                selected_entities.append(val)
        try:
            selected_entities = [int(v) for v in selected_entities]
        except ValueError:
            selected_entities = []
        txn_type = params.get("txn_type", "all")
        ctx["selected_entities"] = selected_entities
        ctx["selected_txn_type"] = txn_type
        ctx["txn_type_choices"] = TXN_TYPE_CHOICES
        # ------------------------------------------------------
        # Top 10 big-ticket transactions within date range
        # ------------------------------------------------------
        qs = Transaction.objects.filter(
            user=self.request.user, date__range=[start_top, end_top]
        )
        if selected_entities:
            qs = qs.filter(
                Q(entity_source_id__in=selected_entities) |
                Q(entity_destination_id__in=selected_entities)
            )
        if txn_type and txn_type != "all":
            qs = qs.filter(transaction_type=txn_type)
        top_entries_qs = (
            qs
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
    