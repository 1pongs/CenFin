from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import date, timedelta
from django.template.defaultfilters import floatformat
from django.contrib.humanize.templatetags.humanize import intcomma
from utils.currency import (
    amount_for_display,
    get_active_currency,
    get_currency_symbol,
    convert_amount,
)
from currencies.models import Currency

from django.db.models import (
    Sum,
    F,
    Case,
    When,
    DecimalField,
    Value,
    IntegerField,
    Count,
)
from collections import defaultdict


from entities.models import Entity
from acquisitions.models import Acquisition
from insurance.forms import InsuranceForm
from insurance.models import Insurance
from accounts.models import Account
from .forms import EntityForm
from transactions.models import Transaction

# ---------------------------------------------------------------------------
# Helper: aggregate_totals
# ---------------------------------------------------------------------------
def get_entity_aggregate_rows(user):
    """Return combined entity totals from both source and destination for a user."""
    base_cur = None
    if getattr(user, "base_currency_id", None):
        base_cur = user.base_currency
    else:
        base_cur = Currency.objects.filter(code="PHP").first()
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

    inflow = Transaction.objects.filter(
        user=user,
        entity_destination__is_active=True,
        entity_destination__is_visible=True,
    ).select_related("currency", "entity_destination")
    for tx in inflow:
        amt = convert_amount(tx.amount or 0, tx.currency, base_cur)
        data = results[tx.entity_destination_id]
        data["the_entity_id"] = tx.entity_destination_id
        data["the_name"] = tx.entity_destination.entity_name
        data["the_type"] = tx.entity_destination.entity_type

        if tx.transaction_type_destination == "Income":
            data["total_income"] += amt
        if tx.transaction_type_destination == "Expense":
            data["total_expenses"] += amt
        if tx.transaction_type_destination == "Transfer":
            data["total_transfer"] += amt
        if tx.transaction_type_destination == "buy_product":
            data["total_asset"] += amt

        if (tx.asset_type_destination or "").lower() == "liquid":
            data["total_liquid"] += amt
        if (tx.asset_type_destination or "").lower() == "non_liquid":
            data["total_non_liquid"] += amt

    outflow = Transaction.objects.filter(
        user=user,
        entity_source__is_active=True,
        entity_source__is_visible=True,
    ).select_related("currency", "entity_source")
    for tx in outflow:
        amt = convert_amount(tx.amount or 0, tx.currency, base_cur)
        data = results[tx.entity_source_id]
        data["the_entity_id"] = tx.entity_source_id
        data["the_name"] = tx.entity_source.entity_name
        data["the_type"] = tx.entity_source.entity_type

        if tx.transaction_type_source == "Income":
            data["total_income"] -= amt
        if tx.transaction_type_source == "Expense":
            data["total_expenses"] -= amt
        if tx.transaction_type_source == "Transfer":
            data["total_transfer"] -= amt
        if tx.transaction_type_source == "sell_product":
            data["total_asset"] -= amt

        if (tx.asset_type_source or "").lower() == "liquid":
            data["total_liquid"] -= amt
        if (tx.asset_type_source or "").lower() == "non_liquid":
            data["total_non_liquid"] -= amt

    # Include all active entities even when no transactions

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

        if not entry["the_name"]:
            entry["the_name"] = ent.entity_name
        if not entry["the_type"]:
            entry["the_type"] = ent.entity_type

    return list(results.values())


# ---------------------------------------------------------------------------
# Helper: acquisition & insurance filtering
# ---------------------------------------------------------------------------
from django.db.models import Q


def filter_acquisitions_for_tab(entity, user, params, category):
    qs = Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(
        user=user, purchase_tx__entity_destination=entity, category=category
    )
    q = params.get("q", "").strip()
    sort = params.get("sort", "name")

    if category == "product":
        if q:
            qs = qs.filter(name__icontains=q)
        if sort == "capital_cost_desc":
            qs = qs.order_by("-purchase_tx__amount")
        else:
            qs = qs.order_by("name")

    elif category == "stock_bond":
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(market__icontains=q))
        market = params.get("market", "").strip()
        if market:
            qs = qs.filter(market=market)
        if sort == "current_value_desc":
            qs = qs.order_by("-current_value")
        else:
            qs = qs.order_by("name")

    elif category == "property":
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(location__icontains=q))
        location = params.get("location", "").strip()
        if location:
            qs = qs.filter(location=location)
        if sort == "expected_lifespan_desc":
            qs = qs.order_by("-expected_lifespan_years")
        else:
            qs = qs.order_by("name")

    elif category == "vehicle":
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(plate_number__icontains=q))
        if sort == "model_year_desc":
            qs = qs.order_by("-model_year")
        elif sort == "mileage_desc":
            qs = qs.order_by("-mileage")
        else:
            qs = qs.order_by("name")

    elif category == "equipment":
        if q:
            qs = qs.filter(name__icontains=q)
        if sort == "expected_lifespan_desc":
            qs = qs.order_by("-expected_lifespan_years")
        else:
            qs = qs.order_by("name")

    return qs


def filter_insurances_for_tab(entity, user, params):
    qs = Insurance.objects.filter(user=user, entity=entity)
    q = params.get("q", "").strip()
    if q:
        qs = qs.filter(Q(policy_owner__icontains=q) | Q(person_insured__icontains=q))
    typ = params.get("type", "").strip()
    if typ:
        qs = qs.filter(insurance_type=typ)
    sort = params.get("sort", "status")
    if sort == "sum_assured_desc":
        qs = qs.order_by("-sum_assured")
    elif sort == "status":
        qs = qs.order_by("status")
    else:
        qs = qs.order_by("policy_owner")
    return qs


class EntityListView(TemplateView):
    template_name = "entities/entity_list.html"

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        from cenfin_proj.utils import get_entity_balances

        ctx = super().get_context_data(**kwargs)

        qs = (
            get_entity_balances()
            .filter(Q(user=self.request.user) | Q(user__isnull=True))
            .exclude(entity_type="outside")
            .filter(is_visible=True)
        )

        params = self.request.GET
        search = params.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(entity_name__icontains=search) | Q(entity_type__icontains=search)
            )

        fund_type = params.get("fund_type", "").strip()
        if fund_type:
            qs = qs.filter(entity_type=fund_type)

        status = params.get("status", "")
        if status in {"active", "inactive"}:
            since = timezone.now().date() - timedelta(days=30)
            tx_qs = Transaction.objects.filter(user=self.request.user, date__gte=since)
            active_ids = set(tx_qs.values_list("entity_source_id", flat=True)) | set(
                tx_qs.values_list("entity_destination_id", flat=True)
            )
            if status == "active":
                qs = qs.filter(pk__in=active_ids)
            else:
                qs = qs.exclude(pk__in=active_ids)

        start_param = params.get("start", "").strip()
        end_param = params.get("end", "").strip()
        start_date = end_date = None
        if start_param:
            try:
                start_date = date.fromisoformat(start_param)
            except ValueError:
                pass
        if end_param:
            try:
                end_date = date.fromisoformat(end_param)
            except ValueError:
                pass
        if start_date or end_date:
            tx_filter = {"user": self.request.user}
            if start_date:
                tx_filter["date__gte"] = start_date
            if end_date:
                tx_filter["date__lte"] = end_date
            tx_qs = Transaction.objects.filter(**tx_filter)
            ids = set(tx_qs.values_list("entity_source_id", flat=True)) | set(
                tx_qs.values_list("entity_destination_id", flat=True)
            )
            qs = qs.filter(pk__in=ids)

        sort = params.get("sort", "name")
        if sort == "balance":
            qs = qs.order_by("-balance", "entity_name")
        elif sort == "date":
            qs = qs.order_by("-pk")
        else:
            qs = qs.order_by("entity_name")

        totals_map = {
            row["the_entity_id"]: row
            for row in get_entity_aggregate_rows(self.request.user)
        }
        active_cur = get_active_currency(self.request)
        symbol = get_currency_symbol(active_cur.code) if active_cur else ""
        base_code = (
            self.request.user.base_currency.code
            if getattr(self.request.user, "base_currency_id", None)
            else ""
        )

        for ent in qs:
            data = totals_map.get(ent.pk, {})
            ent.liquid_total = data.get("total_liquid", 0)
            ent.non_liquid_total = data.get("total_non_liquid", 0)
            
            def _fmt(val):
                conv = amount_for_display(self.request, val, base_code)
                return f"{symbol}{intcomma(floatformat(conv, 2))}"

            ent.card_rows = [
                ("Liquid", _fmt(ent.liquid_total)),
                ("Non-Liquid", _fmt(ent.non_liquid_total)),
            ]

        ctx["entities"] = qs
        ctx["search"] = search
        ctx["fund_type"] = fund_type
        ctx["status"] = status
        ctx["sort"] = sort
        ctx["start"] = start_param
        ctx["end"] = end_param
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

        ctx["insurances"] = Insurance.objects.filter(
            entity=entity, user=self.request.user
        )

        ctx["insurance_form"] = InsuranceForm(
            initial={"entity": entity_pk}, show_actions=False
        )
        
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
    
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if getattr(obj, "is_system_default", False):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("The Accounts entity cannot be modified or removed.")
        if obj.is_account_entity:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Cannot modify Account Entity")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cancel = self.request.GET.get("next") or reverse(
            "entities:accounts", args=[self.object.pk]
        )
        kwargs["cancel_url"] = cancel
        return kwargs

    def get_success_url(self):
        return self.request.GET.get("next") or reverse("entities:list")
    
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
    
    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if getattr(obj, "is_system_default", False):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("The Accounts entity cannot be modified or removed.")
        if obj.is_account_entity:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Cannot delete Account Entity")
        return super().dispatch(request, *args, **kwargs)

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

class EntityAccountsView(TemplateView):
    """Display accounts associated with an entity."""

    template_name = "entities/entity_accounts.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        entity_pk = self.kwargs["pk"]
        entity = get_object_or_404(Entity, pk=entity_pk, user=self.request.user)
        ctx["entity"] = entity

        category = params.get("category", "").strip()
        ctx["current_category"] = category
        qs_copy = params.copy()
        qs_copy.pop("category", None)
        ctx["nav_qs"] = qs_copy.urlencode()

        if not category:
            # ----- Accounts tab -----
            inflow = Transaction.objects.filter(
                user=self.request.user,
                entity_destination_id=entity_pk,
                asset_type_destination__iexact="liquid",
            )
            outflow = Transaction.objects.filter(
                user=self.request.user,
                entity_source_id=entity_pk,
                asset_type_source__iexact="liquid",
            )
            
            inflow = inflow.values(
                "account_destination_id",
                "account_destination__account_name",
            ).annotate(total_in=Sum("amount"), count_in=Count("id"))
            outflow = outflow.values(
                "account_source_id",
                "account_source__account_name",
            ).annotate(total_out=Sum("amount"), count_out=Count("id"))

            balances = {}
            for row in inflow:
                acc_pk = row["account_destination_id"]
                balances[acc_pk] = {
                    "id": acc_pk,
                    "name": row["account_destination__account_name"],
                    "balance": row["total_in"],
                    "tx_count": row["count_in"],
                }
            for row in outflow:
                acc_pk = row["account_source_id"]
                name = row.get("account_source__account_name", "")
                entry = balances.setdefault(
                    acc_pk,
                    {"id": acc_pk, "name": name, "balance": 0, "tx_count": 0},
                )
                if not entry["name"]:
                    entry["name"] = name
                entry["balance"] -= row["total_out"]
                entry["tx_count"] += row["count_out"]

            account_map = {
                acc.id: acc for acc in Account.objects.filter(id__in=balances.keys())
            }
            for pk, data in balances.items():
                acc = account_map.get(pk)
                data["type"] = getattr(acc, "account_type", "") if acc else ""

            results = list(balances.values())
        
            q = params.get("q", "").strip().lower()
            if q:
                results = [r for r in results if q in r["name"].lower()]

            sort = params.get("sort", "name")
            if sort == "balance":
                results.sort(key=lambda x: x["balance"], reverse=True)
            elif sort == "tx_count":
                results.sort(key=lambda x: x.get("tx_count", 0), reverse=True)
            elif sort == "account_type":
                results.sort(key=lambda x: (x.get("type") or "", x["name"]))
            else:
                results.sort(key=lambda x: x["name"])

            ctx["accounts"] = results
            ctx["total_balance"] = sum(b["balance"] for b in results)
            ctx["search"] = params.get("q", "")
            ctx["sort"] = sort
            ctx["insurance_form"] = InsuranceForm(
                initial={"entity": entity_pk}, show_actions=False
            )
            return ctx

        if category == "insurance":
            ins_qs = filter_insurances_for_tab(entity, self.request.user, params)
            ctx["insurances"] = ins_qs
            ctx["search"] = params.get("q", "")
            ctx["sort"] = params.get("sort", "status")
            ctx["type"] = params.get("type", "")
            ctx["type_choices"] = Insurance.TYPE_CHOICES
            ctx["insurance_form"] = InsuranceForm(
                initial={"entity": entity_pk}, show_actions=False
            )
            return ctx

        acqs = filter_acquisitions_for_tab(entity, self.request.user, params, category)
        ctx["acquisitions"] = acqs
        ctx["search"] = params.get("q", "")
        ctx["sort"] = params.get("sort", "name")
        if category == "stock_bond":
            ctx["market"] = params.get("market", "")
            ctx["markets"] = (
                Acquisition.objects.filter(
                    user=self.request.user,
                    purchase_tx__entity_destination=entity,
                    category="stock_bond",
                )
                .exclude(market="")
                .values_list("market", flat=True)
                .distinct()
                .order_by("market")
            )
        elif category == "property":
            ctx["location"] = params.get("location", "")
            ctx["locations"] = (
                Acquisition.objects.filter(
                    user=self.request.user,
                    purchase_tx__entity_destination=entity,
                    category="property",
                )
                .exclude(location="")
                .values_list("location", flat=True)
                .distinct()
                .order_by("location")
            )
        ctx["insurance_form"] = InsuranceForm(
            initial={"entity": entity_pk}, show_actions=False
        )
        return ctx

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