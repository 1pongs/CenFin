from decimal import Decimal

from django.shortcuts import render
from django.views.generic import TemplateView, View
from django.db.models import Case, When, Value, CharField, Q
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
from utils.currency import get_active_currency, convert_to_base

# Create your views here.

class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        base_cur = get_active_currency(self.request)
        ctx["base_currency"] = base_cur
        income = expenses = liquid = asset = liabilities = Decimal("0")
        qs_all = (
            Transaction.objects.filter(user=self.request.user)
            .select_related("currency", "account_destination__currency", "account_destination", "account_source")
        )
        def inflow_base(tx):
            # Prefer destination_amount in the destination account's currency
            if (
                getattr(tx, "destination_amount", None) is not None
                and getattr(tx, "account_destination", None)
                and getattr(tx.account_destination, "currency", None)
            ):
                return convert_to_base(
                    tx.destination_amount or Decimal("0"),
                    tx.account_destination.currency,
                    base_cur,
                    user=self.request.user,
                )
            return convert_to_base(tx.amount or Decimal("0"), tx.currency, base_cur, user=self.request.user)
        def outflow_base(tx):
            return convert_to_base(tx.amount or Decimal("0"), tx.currency, base_cur, user=self.request.user)

        for tx in qs_all:
            tdest = (tx.transaction_type_destination or "").lower()
            tsrc = (tx.transaction_type_source or "").lower()
            adest = (tx.asset_type_destination or "").lower()
            asrc = (tx.asset_type_source or "").lower()
            ttype = (tx.transaction_type or "").lower()
            dest_is_outside = bool(getattr(tx, "account_destination", None) and (tx.account_destination.account_type == "Outside" or tx.account_destination.account_name == "Outside"))
            src_is_outside = bool(getattr(tx, "account_source", None) and (tx.account_source.account_type == "Outside" or tx.account_source.account_name == "Outside"))
            if tdest == "income":
                income += inflow_base(tx)
            if tsrc == "expense":
                expenses += outflow_base(tx)
            # Treat transfer to Outside as moving to non-liquid Asset, and
            # transfer from Outside as moving from Asset (not Liquid).
            if ttype == "transfer" and dest_is_outside:
                asset += inflow_base(tx)
            elif adest == "liquid":
                liquid += inflow_base(tx)
            if ttype == "transfer" and src_is_outside:
                asset -= outflow_base(tx)
            elif asrc == "liquid":
                liquid -= outflow_base(tx)
            if adest == "non_liquid" and not (ttype == "transfer" and dest_is_outside):
                asset += inflow_base(tx)
            elif asrc == "non_liquid" and not (ttype == "transfer" and src_is_outside):
                asset -= outflow_base(tx)

        # Liabilities from loans and credit cards
        from liabilities.models import Loan, CreditCard
        from currencies.models import Currency
        for loan in Loan.objects.filter(user=self.request.user):
            cur = Currency.objects.filter(code=loan.currency).first()
            liabilities += convert_to_base(loan.outstanding_balance or Decimal("0"), cur, base_cur, user=self.request.user)
        for card in CreditCard.objects.filter(user=self.request.user):
            cur = Currency.objects.filter(code=card.currency).first()
            liabilities += convert_to_base(card.outstanding_amount or Decimal("0"), cur, base_cur, user=self.request.user)

        aggregates = {
            "income": income,
            "expenses": expenses,
            "liquid": liquid,
            "asset": asset,
            "liabilities": liabilities,
            "net": liquid + asset - liabilities,
        }

        ctx["totals"] = aggregates

        ctx["cards"] = [
            ("Income",    "income",    "success"),
            ("Expenses",  "expenses",  "danger"),
            ("Liquid", "liquid", "warning"),
            ("Asset", "asset", "info"),
            ("Liabilities", "liabilities", "secondary"),
        ]
        ctx["monthly_summary"] = get_monthly_summary(user=self.request.user, currency=base_cur)
        today = timezone.now().date()
        ctx["today"] = today
        
        ctx["entities"] = Entity.objects.active().filter(user=self.request.user).order_by("entity_name")
        params = self.request.GET

        # Defaults for the date filters used by the charts. These are separate
        # from the possibly user-supplied values so the "Clear Filter" buttons
        # can reset back to the original ranges.
        default_start_cf = today - timedelta(days=365)
        default_end_cf = today
        default_start_top = date(today.year, 1, 1)
        default_end_top = today

        start_cf, end_cf = parse_range_params(self.request, default_start_cf)
        start_top, end_top = parse_range_params(self.request, default_start_top)
        ctx["range_start_cf"] = start_cf
        ctx["range_end_cf"] = end_cf
        ctx["range_start_top"] = start_top
        ctx["range_end_top"] = end_top

        # Defaults used when clearing the filters in the modal dialogs
        ctx["default_range_start_cf"] = default_start_cf
        ctx["default_range_end_cf"] = default_end_cf
        ctx["default_range_start_top"] = default_start_top
        ctx["default_range_end_top"] = default_end_top
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
        ).select_related("currency")
        if selected_entities:
            qs = qs.filter(
                Q(entity_source_id__in=selected_entities)
                | Q(entity_destination_id__in=selected_entities)
            )
        if txn_type and txn_type != "all":
            qs = qs.filter(transaction_type=txn_type)

        entries = []
        for tx in qs:
            amt = convert_to_base(abs(tx.amount or Decimal("0")), tx.currency, base_cur, user=self.request.user)
            if tx.transaction_type_destination == "Income":
                entry_type = "income"
            elif tx.transaction_type_source == "Expense":
                entry_type = "expense"
            elif tx.asset_type_destination == "Non-Liquid":
                entry_type = "asset"
            else:
                entry_type = "other"
            entries.append({"category": tx.description, "amount": amt, "type": entry_type})

        entries.sort(key=lambda r: r["amount"], reverse=True)
        ctx["top10_big_tickets"] = entries[:10]

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
        base_cur = get_active_currency(request)
        data = get_monthly_summary(ent, user=request.user, currency=base_cur)
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

        base_cur = get_active_currency(request)
        data = get_monthly_cash_flow(
            ent, months, drop_empty=True, user=request.user, currency=base_cur
        )
        return JsonResponse(data, safe=False)
    
