from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from django.db.models import Sum, F, Case, When, DecimalField, Value, IntegerField
from collections import defaultdict


from entities.models import Entity
from acquisitions.models import Acquisition
from insurance.forms import InsuranceForm
from insurance.models import Insurance
from .forms import EntityForm
from transactions.models import Transaction

# ---------------------------------------------------------------------------
# Helper: aggregate_totals
# ---------------------------------------------------------------------------
def get_entity_aggregate_rows(user):
    """Return combined entity totals from both source and destination for a user."""
    # 1️⃣ From destination side (inflows)
    dest = (
        Transaction.objects.filter(
            user=user,
            entity_destination__is_active=True,
            entity_destination__is_visible=True,
        )
        .values(
            "entity_destination_id",
            "entity_destination__entity_name",
            "entity_destination__entity_type",
        )
        .annotate(
            total_income=Sum(
                Case(
                    When(transaction_type_destination="Income", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_expenses=Sum(
                Case(
                    When(transaction_type_destination="Expense", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_transfer=Sum(
                Case(
                    When(transaction_type_destination="Transfer", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_asset=Sum(
                Case(
                    When(transaction_type_destination="buy_product", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_liquid=Sum(
                Case(
                    When(asset_type_destination="Liquid", then=F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_non_liquid=Sum(
                Case(
                    When(
                        asset_type_destination__in=["Non-Liquid", "non-liquid", "non_liquid"],
                        then=F("amount"),
                    ),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
        )
    )

    # 2️⃣ From source side (outflows)
    src = (
        Transaction.objects.filter(
            user=user,
            entity_source__is_active=True,
            entity_source__is_visible=True,
        )
        .values(
            "entity_source_id",
            "entity_source__entity_name",
            "entity_source__entity_type",
        )
        .annotate(
            total_income=Sum(
                 Case(
                    When(transaction_type_source="Income", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_expenses=Sum(
                Case(
                    When(transaction_type_source="Expense", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_transfer=Sum(
                Case(
                    When(transaction_type_source="Transfer", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_asset=Sum(
                Case(
                    When(transaction_type_source="sell_product", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_liquid=Sum(
                Case(
                    When(asset_type_source="Liquid", then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
            total_non_liquid=Sum(
                Case(
                    When(
                        asset_type_source__in=["Non-Liquid", "non-liquid", "non_liquid"],
                        then=-F("amount"),
                    ),
                    default=0,
                    output_field=DecimalField(),
                )
            ),
        )
    )

    # 3️⃣ Merge both using a defaultdict
    results = defaultdict(
        lambda: {
            "the_entity_id": None,
            "the_name": "",
            "the_type": "",
            "total_income": 0,
            "total_expenses": 0,
            "total_transfer": 0,
            "total_asset": 0,
            "total_liquid": 0,
            "total_non_liquid": 0,
        }
    )

    for row in list(dest) + list(src):
        id_key = row.get("entity_destination_id") or row.get("entity_source_id")
        name = row.get("entity_destination__entity_name") or row.get(
            "entity_source__entity_name"
        )
        typ = row.get("entity_destination__entity_type") or row.get(
            "entity_source__entity_type"
        )

        data = results[id_key]
        data["the_entity_id"] = id_key
        data["the_name"] = name
        data["the_type"] = typ

        data["total_income"] += row.get("total_income", 0)
        data["total_expenses"] += row.get("total_expenses", 0)
        data["total_transfer"] += row.get("total_transfer", 0)
        data["total_asset"] += row.get("total_asset", 0)
        data["total_liquid"] += row.get("total_liquid", 0)
        data["total_non_liquid"] += row.get("total_non_liquid", 0)

        # 4️⃣ Ensure all active entities are represented even with zero totals
    for ent in Entity.objects.active().filter(user=user, is_visible=True):
        entry = results.setdefault(
            ent.pk,
            {
                "the_entity_id": ent.pk,
                "the_name": ent.entity_name,
                "the_type": ent.entity_type,
                "total_income": 0,
                "total_expenses": 0,
                "total_transfer": 0,
                "total_asset": 0,
                "total_liquid": 0,
                "total_non_liquid": 0,
            },
        )
        # If the entry already existed from transactions, ensure name/type set
        if not entry["the_name"]:
            entry["the_name"] = ent.entity_name
        if not entry["the_type"]:
            entry["the_type"] = ent.entity_type

    return list(results.values())


class EntityListView(TemplateView):
    template_name = "entities/entity_list.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        from cenfin_proj.utils import get_entity_balances

        ctx = super().get_context_data(**kwargs)

        qs = get_entity_balances().filter(
            Q(user=self.request.user) | Q(entity_name="Account")
        ).exclude(entity_type="outside")

        # respect visibility except for the hard-coded Account entity
        qs = qs.filter(Q(is_visible=True) | Q(entity_name="Account"))

        params = self.request.GET
        search = params.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(entity_name__icontains=search)
                | Q(entity_type__icontains=search)
            )

        fund_type = params.get("fund_type", "").strip()
        if fund_type:
            qs = qs.filter(entity_type=fund_type)

        status = params.get("status", "")
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        sort = params.get("sort", "name")
        if sort == "balance":
            qs = qs.order_by("-balance", "entity_name")
        elif sort == "date":
            qs = qs.order_by("-pk")
        else:
            qs = qs.order_by("entity_name")

        ctx["entities"] = qs
        ctx["search"] = search
        ctx["fund_type"] = fund_type
        ctx["status"] = status
        ctx["sort"] = sort
        ctx["start"] = params.get("start", "")
        ctx["end"] = params.get("end", "")
        ctx["fund_types"] = [
            (val, label)
            for val, label in Entity.entities_type_choices
            if val != "outside"
        ]
        ctx["current_type"] = fund_type
        return ctx


# ---------------------------------------------------------------------------
# Detail view per entity
# ---------------------------------------------------------------------------


class EntityDetailView(TemplateView):
    template_name = "entities/entity_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entity_pk = self.kwargs["pk"]

        entity = get_object_or_404(Entity, pk=entity_pk, user=self.request.user)
        ctx["entity"] = entity

        acqs = Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(
            user=self.request.user, purchase_tx__entity_destination=entity
        )
        ctx["acquisitions"] = acqs

        # incoming per account
        inflow = (
            Transaction.objects.filter(
                user=self.request.user,
                entity_destination_id=entity_pk,
                asset_type_destination__iexact="liquid",
            )
            .values("account_destination_id", "account_destination__account_name")
            .annotate(total_in=Sum("amount"))
        )
        # outgoing per account
        outflow = (
            Transaction.objects.filter(
                user=self.request.user,
                entity_source_id=entity_pk,
                asset_type_source__iexact="liquid",
            )
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
            entry = balances.setdefault(acc_pk, {"name": acct_name, "balance": 0})
            if not entry["name"]:
                entry["name"] = acct_name
            entry["balance"] -= row["total_out"]

        ctx["accounts"] = sorted(balances.values(), key=lambda x: x["name"])
        ctx["total_balance"] = sum(b["balance"] for b in balances.values())

        rows = get_entity_aggregate_rows(self.request.user)
        ctx["totals"] = next(
            (row for row in rows if row["the_entity_id"] == entity_pk), None
        )

        ctx["insurances"] = Insurance.objects.filter(entity=entity, user=self.request.user)

        ctx["insurance_form"] = InsuranceForm(initial={"entity": entity_pk})
        
        return ctx


class EntityCreateView(CreateView):
    model = Entity
    form_class = EntityForm
    template_name = "entities/entity_form.html"
    success_url = reverse_lazy("entities:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class EntityUpdateView(UpdateView):
    model = Entity
    form_class = EntityForm
    template_name = "entities/entity_form.html"
    success_url = reverse_lazy("entities:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Entity updated successfully!")
        return response


class EntityDeleteView(DeleteView):
    model = Entity
    template_name = "entities/entity_confirm_delete.html"
    success_url = reverse_lazy("entities:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.delete()
        messages.success(request, "Entity deleted.")
        return redirect(self.success_url)


class EntityArchivedListView(TemplateView):
    template_name = "entities/entity_archived_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["entities"] = Entity.objects.filter(user=self.request.user, is_active=False)
        return ctx


class EntityRestoreView(View):
    def post(self, request, pk):
        ent = get_object_or_404(Entity, pk=pk, user=request.user, is_active=False)
        ent.is_active = True
        ent.save()
        messages.success(request, "Entity restored.")
        return redirect(reverse("entities:archived"))


@require_POST
def api_create_entity(request):
    """Create an entity via AJAX."""
    form = EntityForm(request.POST)
    if form.is_valid():
        ent = form.save(commit=False)
        ent.user = request.user
        ent.save()
        return JsonResponse({"id": ent.pk, "name": ent.entity_name})
    return JsonResponse({"errors": form.errors}, status=400)