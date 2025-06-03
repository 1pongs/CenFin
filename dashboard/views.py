from django.shortcuts import render
from django.views.generic import TemplateView
from django.db.models import Sum, Case, When, F, DecimalField
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
        ctx["latest_tx"] = (
            Transaction.objects
            .select_related("account_source", "account_destination")
            .order_by("-date")[:10]
        )

        ctx["cards"] = [
            ("Income",    "income",    "success"),
            ("Expenses",  "expenses",  "danger"),
            ("Liquid", "liquid", "warning"),
            ("Asset", "asset", "info"),
            ("Net Worth", "net",       "primary"),
        ]
        return ctx