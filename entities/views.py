from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import date, timedelta
from django.conf import settings
from decimal import Decimal
from django.db.models import Sum, Count

from cenfin_proj.utils import get_account_entity_balance
from utils.currency import convert_to_base, get_active_currency


from entities.models import Entity
from acquisitions.models import Acquisition
from accounts.models import Account
from .forms import EntityForm
from transactions.models import Transaction


# ---------------------------------------------------------------------------
# Helper: acquisition filtering
# ---------------------------------------------------------------------------
from django.db.models import Q


def filter_acquisitions_for_tab(entity, user, params, category):
    qs = Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(
        user=user,
        purchase_tx__entity_destination=entity,
        category=category,
        is_deleted=False,
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

        # Status filter removed by request. Entities page now shows visible entities only.

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

        disp_code = getattr(self.request, "display_currency", settings.BASE_CURRENCY)
        from cenfin_proj.utils import get_entity_liquid_nonliquid_totals

        totals = (
            get_entity_liquid_nonliquid_totals(self.request.user, disp_code)
            if disp_code
            else {}
        )

        for ent in qs:
            # Provide both raw and *_display attributes for templates
            t = totals.get(ent.pk, {"liquid": Decimal("0"), "non_liquid": Decimal("0")})
            ent.liquid_total = t["liquid"]
            ent.non_liquid_total = t["non_liquid"]
            ent.liquid_total_display = t["liquid"]
            ent.non_liquid_total_display = t["non_liquid"]

        ctx["entities"] = qs
        ctx["search"] = search
        ctx["fund_type"] = fund_type
    # status removed from UI; keep context clean
        ctx["sort"] = sort
        ctx["start"] = start_param
        ctx["end"] = end_param
        ctx["fund_types"] = [
            (val, label)
            for val, label in Entity.entities_type_choices
            if val != "outside"
        ]
        ctx["current_type"] = fund_type

        # Inline undo banner after delete
        undo_entity_id = self.request.session.pop("undo_entity_id", None)
        undo_entity_name = self.request.session.pop("undo_entity_name", None)
        undo_restore_url = None
        if undo_entity_id is not None:
            try:
                undo_restore_url = reverse("entities:restore", args=[undo_entity_id])
            except Exception:
                undo_restore_url = None
        ctx["undo_entity_name"] = undo_entity_name
        ctx["undo_restore_url"] = undo_restore_url
        return ctx


# ---------------------------------------------------------------------------
# Detail view per entity
# ---------------------------------------------------------------------------


class EntityDetailView(TemplateView):
    template_name = "entities/entity_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entity_pk = self.kwargs["pk"]

        entity = get_object_or_404(
            Entity, pk=entity_pk, user=self.request.user, is_active=True
        )
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
        restore_url = reverse("entities:restore", args=[obj.pk])
        messages.success(
            request,
            "Entity deleted. "
            + f'<a href="{restore_url}" class="ms-2 btn btn-sm btn-light">Undo</a>',
            extra_tags="safe",
        )
        # Persist inline banner on list
        request.session["undo_entity_id"] = obj.pk
        request.session["undo_entity_name"] = obj.entity_name
        return redirect(self.success_url)


class EntityArchivedListView(TemplateView):
    """Deprecated: archived view removed globally."""
    template_name = "entities/entity_archived_list.html"

    def dispatch(self, request, *args, **kwargs):
        return redirect(reverse("entities:list"))


class EntityRestoreView(View):
    def _restore(self, request, pk):
        ent = get_object_or_404(Entity, pk=pk, user=request.user, is_active=False)
        ent.is_active = True
        ent.save()
        messages.success(request, "Entity restored.")
        return redirect(reverse("entities:list"))

    def post(self, request, pk):
        return self._restore(request, pk)

    def get(self, request, pk):
        return self._restore(request, pk)


class EntityAccountsView(TemplateView):
    """Display accounts associated with an entity."""

    template_name = "entities/entity_accounts.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        entity_pk = self.kwargs["pk"]
        entity = get_object_or_404(
            Entity, pk=entity_pk, user=self.request.user, is_active=True
        )
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
                parent_transfer__isnull=True,
                is_deleted=False,
                is_reversal=False,
                entity_destination_id=entity_pk,
                asset_type_destination__iexact="liquid",
            )
            outflow = Transaction.objects.filter(
                user=self.request.user,
                parent_transfer__isnull=True,
                is_deleted=False,
                is_reversal=False,
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
                    "tx_count": row["count_in"],
                }
            for row in outflow:
                acc_pk = row["account_source_id"]
                name = row.get("account_source__account_name", "")
                entry = balances.setdefault(
                    acc_pk,
                    {"id": acc_pk, "name": name, "tx_count": 0},
                )
                if not entry["name"]:
                    entry["name"] = name
                entry["tx_count"] += row["count_out"]

            account_map = {
                acc.id: acc for acc in Account.objects.filter(id__in=balances.keys())
            }
            for pk, data in balances.items():
                acc = account_map.get(pk)
                data["type"] = getattr(acc, "account_type", "") if acc else ""
                data["currency"] = acc.currency if acc else None
                data["balance"] = get_account_entity_balance(
                    pk, entity_pk, user=self.request.user
                )

            results = list(balances.values())
            # Hide the special Outside account from the entity Accounts list
            results = [
                r
                for r in results
                if (r.get("type") != "Outside" and (r.get("name") or "") != "Outside")
            ]

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

            disp_code = getattr(
                self.request, "display_currency", settings.BASE_CURRENCY
            )
            total_balance = Decimal("0")
            for row in results:
                bal = row.get("balance") or Decimal("0")
                cur = row.get("currency")
                if cur:
                    total_balance += convert_to_base(
                        bal, cur, base_currency=disp_code, user=self.request.user
                    )
                else:
                    total_balance += bal

            ctx["accounts"] = results
            ctx["total_balance"] = total_balance
            ctx["search"] = params.get("q", "")
            ctx["sort"] = sort
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


# -------------------- Analytics --------------------


class EntityAnalyticsView(TemplateView):
    template_name = "entities/entity_analytics.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entity_pk = self.kwargs["pk"]
        entity = get_object_or_404(
            Entity, pk=entity_pk, user=self.request.user, is_active=True
        )
        ctx["entity"] = entity
        active = get_active_currency(self.request)
        ctx["display_currency"] = (
            active.code
            if active
            else (getattr(self.request.user, "base_currency", None) or "PHP")
        )
        return ctx


def _parse_dates(request):
    from datetime import datetime

    fmt = "%Y-%m-%d"
    start_s = request.GET.get("start")
    end_s = request.GET.get("end")
    start = end = None
    try:
        if start_s:
            start = datetime.strptime(start_s, fmt).date()
    except Exception:
        start = None
    try:
        if end_s:
            end = datetime.strptime(end_s, fmt).date()
    except Exception:
        end = None
    return start, end


def entity_kpis(request, pk):
    entity = get_object_or_404(Entity, pk=pk, user=request.user, is_active=True)
    start, end = _parse_dates(request)

    q_base = Transaction.objects.filter(user=request.user, parent_transfer__isnull=True)
    if start:
        q_base = q_base.filter(date__gte=start)
    if end:
        q_base = q_base.filter(date__lte=end)

    # Income: true income only (exclude transfers/capital). Use mapped dest type.
    income_qs = q_base.filter(
        entity_destination=entity,
        asset_type_destination__iexact="liquid",
        transaction_type_destination__iexact="Income",
    ).select_related("currency")
    # Expenses: true expenses only (exclude transfers)
    expense_qs = q_base.filter(
        entity_source=entity,
        asset_type_source__iexact="liquid",
        transaction_type_source__iexact="Expense",
    ).select_related("currency")
    # Capital: net transfers (in - out)
    cap_in_qs = q_base.filter(
        entity_destination=entity,
        asset_type_destination__iexact="liquid",
        transaction_type__iexact="transfer",
    ).select_related("currency")
    cap_out_qs = q_base.filter(
        entity_source=entity,
        asset_type_source__iexact="liquid",
        transaction_type__iexact="transfer",
    ).select_related("currency")

    def inflow_amount_and_currency(tx):
        # Use destination_amount when present; it is denominated in the
        # destination account's currency, not tx.currency.
        if (
            tx.destination_amount is not None
            and tx.account_destination
            and getattr(tx.account_destination, "currency", None)
        ):
            return tx.destination_amount, tx.account_destination.currency
        return (tx.amount, tx.currency)

    income = sum(
        (
            convert_to_base(
                *inflow_amount_and_currency(tx), request=request, user=request.user
            )
            for tx in income_qs
        ),
        Decimal("0"),
    )
    expenses = sum(
        (
            convert_to_base(
                tx.amount or 0, tx.currency, request=request, user=request.user
            )
            for tx in expense_qs
        ),
        Decimal("0"),
    )
    capital_in = sum(
        (
            convert_to_base(
                *inflow_amount_and_currency(tx), request=request, user=request.user
            )
            for tx in cap_in_qs
        ),
        Decimal("0"),
    )
    capital_out = sum(
        (
            convert_to_base(
                tx.amount or 0, tx.currency, request=request, user=request.user
            )
            for tx in cap_out_qs
        ),
        Decimal("0"),
    )
    capital_net = capital_in - capital_out
    return JsonResponse(
        {
            "income": str(income),
            "expenses": str(expenses),
            "capital": str(capital_net),
            "net": str(income - expenses),
            "currency": (
                get_active_currency(request).code
                if get_active_currency(request)
                else "PHP"
            ),
        }
    )


def entity_category_summary_api(request, pk):
    entity = get_object_or_404(Entity, pk=pk, user=request.user, is_active=True)
    start, end = _parse_dates(request)
    mode = (request.GET.get("type") or "expense").lower()
    q = (
        Transaction.objects.filter(user=request.user, parent_transfer__isnull=True)
        .prefetch_related("categories")
        .select_related("currency")
    )
    if start:
        q = q.filter(date__gte=start)
    if end:
        q = q.filter(date__lte=end)
    if mode == "income":
        # Only true income
        q = q.filter(
            entity_destination=entity,
            asset_type_destination__iexact="liquid",
            transaction_type_destination__iexact="Income",
        )

        def get_amount_and_currency(tx):
            if (
                tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
            ):
                return tx.destination_amount, tx.account_destination.currency
            return tx.amount, tx.currency

    elif mode == "transfer":
        # Transfers treated as capital inflows to destination entity
        q = q.filter(
            entity_destination=entity,
            asset_type_destination__iexact="liquid",
            transaction_type__iexact="transfer",
        )

        def get_amount_and_currency(tx):
            if (
                tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
            ):
                return tx.destination_amount, tx.account_destination.currency
            return tx.amount, tx.currency

    else:
        # Only true expenses
        q = q.filter(
            entity_source=entity,
            asset_type_source__iexact="liquid",
            transaction_type_source__iexact="Expense",
        )

        def get_amount_and_currency(tx):
            return tx.amount, tx.currency

    totals = {}
    for tx in q:
        cats = list(tx.categories.all())
        if not cats:
            continue
        amt_val, amt_cur = get_amount_and_currency(tx)
        amt = convert_to_base(amt_val or 0, amt_cur, request=request, user=request.user)
        for c in cats:
            totals[c.name] = totals.get(c.name, Decimal("0")) + amt
    # Return top N by amount, ordered desc
    data = sorted(
        ({"name": k, "total": str(v)} for k, v in totals.items()),
        key=lambda r: Decimal(r["total"]),
        reverse=True,
    )
    return JsonResponse(data, safe=False)


def entity_category_timeseries_api(request, pk):
    entity = get_object_or_404(Entity, pk=pk, user=request.user)
    start, end = _parse_dates(request)
    category = request.GET.get("category")  # name or id
    _interval = request.GET.get("interval", "month")  # future-proof

    q = (
        Transaction.objects.filter(user=request.user, parent_transfer__isnull=True)
        .prefetch_related("categories")
        .select_related("currency")
    )
    if start:
        q = q.filter(date__gte=start)
    if end:
        q = q.filter(date__lte=end)
    mode = (request.GET.get("type") or "expense").lower()
    if mode == "income":
        q = q.filter(
            entity_destination=entity,
            asset_type_destination__iexact="liquid",
            transaction_type_destination__iexact="Income",
        )

        def get_amount_and_currency(tx):
            if (
                tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
            ):
                return tx.destination_amount, tx.account_destination.currency
            return tx.amount, tx.currency

    elif mode == "transfer":
        q = q.filter(
            entity_destination=entity,
            asset_type_destination__iexact="liquid",
            transaction_type__iexact="transfer",
        )

        def get_amount_and_currency(tx):
            if (
                tx.destination_amount is not None
                and tx.account_destination
                and getattr(tx.account_destination, "currency", None)
            ):
                return tx.destination_amount, tx.account_destination.currency
            return tx.amount, tx.currency

    else:
        # Expenses by default (true expenses only)
        q = q.filter(
            entity_source=entity,
            asset_type_source__iexact="liquid",
            transaction_type_source__iexact="Expense",
        )

        def get_amount_and_currency(tx):
            return tx.amount, tx.currency

    # Filter by category name or id
    if category:
        try:
            # allow numeric id
            cat_id = int(category)
            q = q.filter(categories__id=cat_id)
        except (ValueError, TypeError):
            q = q.filter(categories__name=category)

    buckets = {}
    for tx in q:
        key = tx.date.replace(day=1)
        val, cur = get_amount_and_currency(tx)
        amt = convert_to_base(val or 0, cur, request=request, user=request.user)
        buckets[key] = buckets.get(key, Decimal("0")) + amt

    rows = sorted(
        (
            {"period": d.strftime("%Y-%m-01"), "total": str(v)}
            for d, v in buckets.items()
        ),
        key=lambda r: r["period"],
    )
    return JsonResponse(rows, safe=False)
