from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, CreateView
from django.urls import reverse_lazy
from django.db.models import Sum, F, Case, When, DecimalField, Value, IntegerField
from collections import defaultdict


from entities.models import Entity
from .forms import EntityForm
from transactions.models import Transaction

# ---------------------------------------------------------------------------
# Helper: aggregate_totals
# ---------------------------------------------------------------------------
def get_entity_aggregate_rows():
    """Return combined entity totals from both source and destination."""
    # 1️⃣ From destination side (inflows)
    dest = (
        Transaction.objects
        .values(
            "entity_destination_id",
            "entity_destination__entity_name",
            "entity_destination__entity_type"
        )
        .annotate(
            total_income=Sum(
                Case(When(transaction_type_destination="Income", then=F("amount")), default=0, output_field=DecimalField())
            ),
            total_expenses=Sum(
                Case(When(transaction_type_destination="Expense", then=F("amount")), default=0, output_field=DecimalField())
            ),
            total_transfer=Sum(
                Case(When(transaction_type_destination="Transfer", then=F("amount")), default=0, output_field=DecimalField())
            ),
            total_asset=Sum(
                Case(When(transaction_type_destination="Buy Asset", then=F("amount")), default=0, output_field=DecimalField())
            ),
            total_liquid=Sum(
                Case(When(asset_type_destination="Liquid", then=F("amount")), default=0, output_field=DecimalField())
            ),
            total_non_liquid=Sum(
                Case(When(asset_type_destination="Non-Liquid", then=F("amount")), default=0, output_field=DecimalField())
            ),
        )
    )

    # 2️⃣ From source side (outflows)
    src = (
        Transaction.objects
        .values(
            "entity_source_id",
            "entity_source__entity_name",
            "entity_source__entity_type"
        )
        .annotate(
            total_income=Sum(
                Case(When(transaction_type_source="Income", then=-F("amount")), default=0, output_field=DecimalField())
            ),
            total_expenses=Sum(
                Case(When(transaction_type_source="Expense", then=-F("amount")), default=0, output_field=DecimalField())
            ),
            total_transfer=Sum(
                Case(When(transaction_type_source="Transfer", then=-F("amount")), default=0, output_field=DecimalField())
            ),
            total_asset=Sum(
                Case(When(transaction_type_source="Sell Asset", then=-F("amount")), default=0, output_field=DecimalField())
            ),
            total_liquid=Sum(
                Case(When(asset_type_source="Liquid", then=-F("amount")), default=0, output_field=DecimalField())
            ),
            total_non_liquid=Sum(
                Case(When(asset_type_source="Non-Liquid", then=-F("amount")), default=0, output_field=DecimalField())
            ),
        )
    )

    # 3️⃣ Merge both using a defaultdict
    results = defaultdict(lambda: {
        "the_entity_id": None,
        "the_name": "",
        "the_type": "",
        "total_income": 0,
        "total_expenses": 0,
        "total_transfer": 0,
        "total_asset": 0,
        "total_liquid": 0,
        "total_non_liquid": 0,
    })

    for row in list(dest) + list(src):
        id_key = row.get("entity_destination_id") or row.get("entity_source_id")
        name = row.get("entity_destination__entity_name") or row.get("entity_source__entity_name")
        typ = row.get("entity_destination__entity_type") or row.get("entity_source__entity_type")

        data = results[id_key]
        data["the_entity_id"] = id_key
        data["the_name"] = name
        data["the_type"] = typ

        data["total_income"]       += row.get("total_income", 0)
        data["total_expenses"]     += row.get("total_expenses", 0)
        data["total_transfer"]     += row.get("total_transfer", 0)
        data["total_asset"]        += row.get("total_asset", 0)
        data["total_liquid"]       += row.get("total_liquid", 0)
        data["total_non_liquid"]   += row.get("total_non_liquid", 0)

    return list(results.values())

class EntityListView(TemplateView):
    template_name = "entities/entity_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        rows = get_entity_aggregate_rows()

        search = self.request.GET.get("q", "").strip().lower()
        if search:
            rows = [r for r in rows if search in r["the_name"].lower()]

        sort = self.request.GET.get("sort", "name")
        if sort == "-name":
            rows.sort(key=lambda r: r["the_name"], reverse=True)
        elif sort == "type":
            rows.sort(key=lambda r: r["the_type"])
        elif sort == "-type":
            rows.sort(key=lambda r: r["the_type"], reverse=True)
        else:
            # default sort by name ascending
            rows.sort(key=lambda r: r["the_name"])

        ctx["name_next"] = "-name" if sort == "name" else "name"
        ctx["type_next"] = "-type" if sort == "type" else "type"

        ctx["entities"] = rows
        ctx["search"] = self.request.GET.get("q", "")
        ctx["sort"] = sort
        return ctx

# ---------------------------------------------------------------------------
# Detail view per entity
# ---------------------------------------------------------------------------

class EntityAccountDetailView(TemplateView):
    template_name = "entities/entity_accounts.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entity_pk = self.kwargs["pk"]

        entity = get_object_or_404(Entity, pk=entity_pk)
        ctx["entity"] = entity

        # incoming per account
        inflow = (
            Transaction.objects.filter(entity_destination_id=entity_pk)
            .values("account_destination_id", "account_destination__account_name")
            .annotate(total_in=Sum("amount"))
        )
        # outgoing per account
        outflow = (
            Transaction.objects.filter(entity_source_id=entity_pk)
            .values("account_source_id", "account_source__account_name")
            .annotate(total_out=Sum("amount"))
        )

        balances = {}
        for row in inflow:
            acc_pk = row["account_destination_id"]
            balances[acc_pk] = {
                "name": row["account_destination__account_name"],
                "balance": row["total_in"],
            }
        for row in outflow:
            acc_pk = row["account_source_id"]
            acct_name = row.get("account_source__account_name", "")
            entry = balances.setdefault(acc_pk, {"name": acct_name, "balance":0})
            if not entry["name"]:
                entry["name"] = acct_name
            entry["balance"] -= row["total_out"]

        ctx["accounts"] = sorted(balances.values(), key=lambda x: x["name"])

        rows = get_entity_aggregate_rows()
        ctx["totals"] = next((row for row in rows if row["the_entity_id"] == entity_pk), None)

        return ctx


class EntityCreateView(CreateView):
    model = Entity
    form_class = EntityForm
    template_name = "entities/entity_form.html"
    success_url = reverse_lazy("entities:list")