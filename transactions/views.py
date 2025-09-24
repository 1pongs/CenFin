from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from decimal import Decimal

from django.http import HttpResponseRedirect, JsonResponse, QueryDict
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Case, When, DecimalField, F, Q
import json
from cenfin_proj.utils import (
    get_account_entity_balance,
    get_entity_balance as util_entity_balance,
    get_account_balance,
    get_entity_liquid_nonliquid_totals,
)
from utils.currency import get_active_currency, convert_amount, convert_to_base

from .models import Transaction, TransactionTemplate, CategoryTag
from .forms import TransactionForm, TemplateForm
from accounts.forms import AccountForm
from accounts.utils import ensure_remittance_account
from entities.utils import ensure_remittance_entity
from entities.forms import EntityForm
from accounts.models import Account
from entities.models import Entity
from liabilities.models import Loan

from .constants import TXN_TYPE_CHOICES, CATEGORY_SCOPE_BY_TX, ASSET_TYPE_CHOICES
import logging
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model, login as auth_login

logger = logging.getLogger("transactions")

# Create your views here.


def _reverse_and_hide(txn, actor=None):
    """Create reversal entry/entries for a transaction then hide the original.

    - Reversal entries are always hidden and flagged with `is_reversal=True`.
    - Original entries are marked as reversed exactly once.
    - If the transaction is already a reversal or already reversed, this is a no-op.
    """
    if getattr(txn, "is_reversal", False) or getattr(txn, "is_reversed", False):
        return

    related = [txn] + list(Transaction.all_objects.filter(parent_transfer=txn))
    rev_parent = None
    for original in related:
        if getattr(original, "is_reversal", False) or getattr(
            original, "is_reversed", False
        ):
            continue
        has_both = bool(original.account_source_id and original.account_destination_id)
        if has_both and original.destination_amount is not None:
            amount = original.destination_amount
            dest_amount = original.amount
        else:
            amount = original.amount
            dest_amount = None

        rev = Transaction.objects.create(
            user=original.user,
            date=timezone.now().date(),
            description=f"Reversal of {original.description}",
            transaction_type=original.transaction_type,
            amount=amount,
            destination_amount=dest_amount,
            account_source=original.account_destination,
            account_destination=original.account_source,
            entity_source=original.entity_destination,
            entity_destination=original.entity_source,
            currency=original.currency,
            parent_transfer=rev_parent if original is not txn else None,
            # Reversal rows are hidden by default. Use the manager helper
            # `include_reversals()` or `all_objects` to discover them when
            # needed (undo, audits, tests).
            is_hidden=True,
            is_reversal=True,
            reversed_transaction=original,
        )
        if original is txn:
            rev_parent = rev
        # mark original as reversed (use all_objects to bypass default manager filter)
        updates = {
            "is_reversed": True,
            "reversed_at": timezone.now(),
            "ledger_status": "reversed",
        }
        if actor is not None:
            updates["reversed_by"] = actor
        # Perform an update query to avoid base manager filtering out hidden rows
        Transaction.all_objects.filter(pk=original.pk).update(**updates)

    Transaction.all_objects.filter(Q(pk=txn.pk) | Q(parent_transfer=txn)).update(
        is_hidden=True
    )


@login_required
def transaction_undo_delete(request, pk):
    """Undo a prior delete by un-hiding the original and removing reversals.

    We only allow undo for the given transaction id that was previously
    reversed-and-hidden by our delete flow.
    """
    original = get_object_or_404(Transaction.all_objects, pk=pk, user=request.user)
    # Identify the original and any hidden child legs
    related = [original] + list(
        Transaction.all_objects.filter(parent_transfer=original)
    )
    # Ensure these were actually reversed/hidden
    if not all(getattr(t, "is_hidden", False) for t in related):
        messages.info(request, "Nothing to undo.")
        return redirect(reverse("transactions:transaction_list"))

    # Delete reversal rows for each related original
    Transaction.all_objects.filter(
        reversed_transaction__in=[t.pk for t in related]
    ).delete()

    # Unhide originals and clear reversed flags
    for t in related:
        t.is_hidden = False
        t.is_reversed = False
        t.reversed_at = None
        t.reversed_by = None
        t.ledger_status = "posted"
        t.save(
            update_fields=[
                "is_hidden",
                "is_reversed",
                "reversed_at",
                "reversed_by",
                "ledger_status",
            ]
        )

    messages.success(request, "Transaction restore complete.")
    return redirect(reverse("transactions:transaction_list"))


class TemplateDropdownMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["templates"] = TransactionTemplate.objects.filter(user=self.request.user)
        return ctx


# ------------- transactions -----------------
class TransactionListView(ListView):
    model = Transaction
    template_name = "transactions/transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        params = self.request.GET
        # Archived view removed globally: always show active, visible transactions only
        qs = (
            super()
            .get_queryset()
            .filter(user=self.request.user)
            .select_related("currency", "account_destination__currency")
        )
        # Do not display reversal entries in the list
        qs = qs.filter(is_reversal=False).exclude(
            description__istartswith="reversal of"
        )
        # Also hide acquisition-linked rows when the acquisition has been
        # soft-deleted. This ensures deleting an acquisition removes its
        # buy/sell rows from the active list even if other flags did not
        # hide them for some reason.
        try:
            qs = qs.exclude(acquisition_purchase__is_deleted=True).exclude(
                acquisition_sale__is_deleted=True
            )
        except Exception:
            # If the relations are unavailable, proceed without this filter.
            pass
        params = self.request.GET

        # Pair filter: when both account and entity are provided, show
        # transactions involving that specific pair in either direction.
        pair_account = params.get("account")
        pair_entity = params.get("entity")
        if pair_account and pair_entity:
            # Pair filter: only rows where BOTH the specified account and
            # entity occur on the same side (source or destination).
            qs = qs.filter(
                Q(account_source_id=pair_account, entity_source_id=pair_entity)
                | Q(
                    account_destination_id=pair_account,
                    entity_destination_id=pair_entity,
                )
            )

        search = params.get("q", "").strip()
        if search:
            qs = qs.filter(description__icontains=search)

        sort = params.get("sort", "-date")
        if sort not in ["-date", "date", "amount", "-amount"]:
            sort = "-date"

        tx_type = params.get("transaction_type")
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)

        # Unified filters: account/entity should match either source or destination.
        # Backward compatibility: still honor old per-side params if provided.
        account_any = params.get("account")
        entity_any = params.get("entity")

        acc_src = params.get("account_source")
        acc_dest = params.get("account_destination")
        ent_src = params.get("entity_source")
        ent_dest = params.get("entity_destination")

        if account_any:
            qs = qs.filter(
                Q(account_source_id=account_any) | Q(account_destination_id=account_any)
            )
        else:
            if acc_src:
                qs = qs.filter(account_source_id=acc_src)
            if acc_dest:
                qs = qs.filter(account_destination_id=acc_dest)

        if entity_any:
            qs = qs.filter(
                Q(entity_source_id=entity_any) | Q(entity_destination_id=entity_any)
            )
        else:
            if ent_src:
                qs = qs.filter(entity_source_id=ent_src)
            if ent_dest:
                qs = qs.filter(entity_destination_id=ent_dest)

        # Asset type filter: show rows where either side matches the selected
        # asset class ("liquid", "non_liquid", or "credit"). Accept dash/underscore forms.
        asset_type = params.get("asset_type", "").strip().lower()
        if asset_type:
            at = asset_type.replace("-", "_")
            if at in {"liquid", "non_liquid", "credit"}:
                # Accept hyphenated legacy values as well
                variants = [at]
                if at == "non_liquid":
                    variants.append("non-liquid")

                cond = Q()
                for v in variants:
                    cond = cond | Q(asset_type_source__iexact=v) | Q(
                        asset_type_destination__iexact=v
                    )

                # Fallbacks for legacy/misaligned mappings on acquisition rows
                if at == "non_liquid":
                    acq_types_ci = (
                        Q(transaction_type__iexact="buy acquisition")
                        | Q(transaction_type__iexact="sell acquisition")
                        | Q(transaction_type__iexact="buy_acquisition")
                        | Q(transaction_type__iexact="sell_acquisition")
                    )
                    cond = cond | acq_types_ci
                    # Either side missing mapping should still qualify as acquisition-related
                    cond = cond | (acq_types_ci & Q(asset_type_source__isnull=True))
                    cond = cond | (acq_types_ci & Q(asset_type_destination__isnull=True))
                    # Legacy conversion rows recorded as simple transfers:
                    # include those as Non‑Liquid when they represent a
                    # conversion to/from Outside for the same entity. Do not
                    # rely on description text; match by Outside account and
                    # same entity on both sides. When an entity filter is
                    # present, scope to that entity explicitly.
                    legacy_conv = (
                        Q(transaction_type__iexact="transfer")
                        & Q(entity_source_id=F("entity_destination_id"))
                        & (
                            Q(account_source__account_name__iexact="Outside")
                            | Q(account_destination__account_name__iexact="Outside")
                        )
                    )
                    try:
                        ent_any = (params.get("entity") or "").strip()
                        if ent_any:
                            legacy_conv = legacy_conv & (
                                Q(entity_source_id=ent_any) | Q(entity_destination_id=ent_any)
                            )
                    except Exception:
                        pass
                    cond = cond | legacy_conv

                qs = qs.filter(cond)

        date_range = params.get("date_range")
        today = timezone.now().date()
        if date_range == "last7":
            qs = qs.filter(date__gte=today - timedelta(days=7))
        elif date_range == "last30":
            qs = qs.filter(date__gte=today - timedelta(days=30))
        elif date_range == "month":
            qs = qs.filter(date__year=today.year, date__month=today.month)

        # Enforce stable tie-breakers: for same date, newer creations first; for amount,
        # fall back to date then creation time so ordering feels consistent.
        if sort == "-date":
            order = ["-date", "-posted_at", "-id"]
        elif sort == "date":
            order = ["date", "posted_at", "id"]
        elif sort == "-amount":
            order = ["-amount", "-date", "-posted_at", "-id"]
        else:  # sort == "amount"
            order = ["amount", "date", "posted_at", "id"]

        return qs.order_by(*order)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        active = get_active_currency(self.request)
        disp_code = active.code if active else settings.BASE_CURRENCY

        ctx["display_currency"] = disp_code
        ctx["accounts"] = (
            Account.objects.active()
            .filter(user=self.request.user, system_hidden=False)
            .exclude(account_name__istartswith="Remittance")
        )
        ctx["entities"] = Entity.objects.active().filter(user=self.request.user)
        ctx["txn_type_choices"] = TXN_TYPE_CHOICES
        ctx["asset_type_choices"] = ASSET_TYPE_CHOICES
        params = self.request.GET
        ctx["search"] = params.get("q", "")
        ctx["sort"] = params.get("sort", "-date")
        # Archived flag removed globally

        # Back link to the entity accounts page when filtered by a specific
        # account/entity pair.
        pair_entity = params.get("entity")
        pair_account = params.get("account")
        if pair_entity and pair_account:
            try:
                ent_id = int(pair_entity)
                ctx["back_url"] = reverse("entities:accounts", args=[ent_id])
            except Exception:
                pass
        # Inline undo banner after delete
        undo_txn_id = self.request.session.pop("undo_txn_id", None)
        undo_txn_desc = self.request.session.pop("undo_txn_desc", None)
        undo_restore_url = None
        if undo_txn_id is not None:
            try:
                undo_restore_url = reverse(
                    "transactions:transaction_undo_delete", args=[undo_txn_id]
                )
            except Exception:
                undo_restore_url = None
        ctx["undo_txn_desc"] = undo_txn_desc
        ctx["undo_restore_url"] = undo_restore_url

        # Summary: count and optional total in display currency when key filters are applied
        params = self.request.GET
        filters_applied = any(
            params.get(k)
            for k in [
                "account",
                "entity",
                "asset_type",
                "transaction_type",
                # Back-compat params
                "account_source",
                "account_destination",
                "entity_source",
                "entity_destination",
            ]
        )
        try:
            obj_list = list(ctx.get("transactions", []))
        except Exception:
            obj_list = []
        ctx["txn_count"] = len(obj_list)
        ctx["filters_applied"] = filters_applied
        if filters_applied and obj_list:
            total = Decimal("0")
            # Scope-aware netting: add when matching destination; subtract when matching source.
            acc_any = params.get("account")
            ent_any = params.get("entity")
            tx_type_filter = params.get("transaction_type")
            # Respect asset_type filter when present: only count sides that match
            asset_filter_raw = (params.get("asset_type") or "").strip().lower()
            asset_filter = asset_filter_raw.replace("-", "_") if asset_filter_raw else ""
            if asset_filter not in {"liquid", "non_liquid", "credit"}:
                asset_filter = ""

            # When ONLY Entity is selected (no account filters, no type, no asset filter),
            # show the entity's current holdings (liquid + non‑liquid), matching the
            # Entities page so this list can serve as a cross‑check tool.
            if ent_any and not any([acc_any, params.get("account_source"), params.get("account_destination"), params.get("entity_source"), params.get("entity_destination"), tx_type_filter, asset_filter]):
                try:
                    ent_id = int(ent_any)
                except (TypeError, ValueError):
                    ent_id = None
                if ent_id:
                    try:
                        totals = get_entity_liquid_nonliquid_totals(self.request.user, disp_code)
                        lt = totals.get(ent_id, {}).get("liquid", Decimal("0"))
                        nlt = totals.get(ent_id, {}).get("non_liquid", Decimal("0"))
                        ctx["summary_total"] = lt + nlt
                        # Provide subtotals in context for optional UI badges
                        ctx["entity_liquid_total"] = lt
                        ctx["entity_non_liquid_total"] = nlt
                        return ctx
                    except Exception:
                        pass

            # When both an Entity and a specific asset_type are selected, compute the
            # summary using the same rules as the Entity card so numbers match exactly.
            if ent_any and asset_filter in {"liquid", "non_liquid"}:
                try:
                    ent_id = int(ent_any)
                except (TypeError, ValueError):
                    ent_id = None
                if ent_id:
                    try:
                        totals = get_entity_liquid_nonliquid_totals(self.request.user, disp_code)
                        bucket = "liquid" if asset_filter == "liquid" else "non_liquid"
                        ctx["summary_total"] = totals.get(ent_id, {}).get(bucket, Decimal("0"))
                        return ctx
                    except Exception:
                        # If helper fails, fall back to local computation below
                        pass
            # When only Entity is selected (no specific asset_type), include both
            # liquid and non‑liquid in the computation so users see overall net.
            if ent_any and not asset_filter:
                asset_filter = ""

            # Fast path: when filtering by transaction_type only (no account/entity scoping),
            # the summary should reflect the sum of amounts shown in the Amount column.
            # The table displays tx.amount converted to the active display currency.
            acc_src = params.get("account_source")
            acc_dest = params.get("account_destination")
            ent_src = params.get("entity_source")
            ent_dest = params.get("entity_destination")
            only_type = bool(tx_type_filter) and not any(
                [acc_any, ent_any, acc_src, acc_dest, ent_src, ent_dest]
            )
            if only_type:
                try:
                    total = sum(
                        convert_to_base(
                            getattr(tx, "amount", Decimal("0")) or Decimal("0"),
                            getattr(tx, "currency", None),
                            request=self.request,
                            user=self.request.user,
                        )
                        for tx in obj_list
                    )
                except Exception:
                    # If any conversion fails, fall back to 0 for that row
                    total = Decimal("0")
                    for tx in obj_list:
                        try:
                            total += convert_to_base(
                                getattr(tx, "amount", Decimal("0")) or Decimal("0"),
                                getattr(tx, "currency", None),
                                request=self.request,
                                user=self.request.user,
                            )
                        except Exception:
                            continue
                ctx["summary_total"] = total
                return ctx

            def _legacy_non_liquid_src(tx):
                """Treat certain legacy transfers as Non‑Liquid on the source side.

                Pattern: a plain transfer involving the same entity on both sides
                with an Outside leg (either source or destination account named
                'Outside'). This commonly represents capital return when paired
                with a sale, and should reduce Non‑Liquid for that entity.
                """
                if asset_filter != "non_liquid":
                    return False
                try:
                    tx_type = (getattr(tx, "transaction_type", "") or "").lower()
                    if tx_type != "transfer":
                        return False
                    es = getattr(tx, "entity_source_id", None)
                    ed = getattr(tx, "entity_destination_id", None)
                    if not es or not ed or es != ed:
                        return False
                    # If an entity filter is applied, scope to that entity
                    if ent_any and str(es) != str(ent_any) and str(ed) != str(ent_any):
                        return False
                    an_src = getattr(getattr(tx, "account_source", None), "account_name", "") or ""
                    an_dst = getattr(getattr(tx, "account_destination", None), "account_name", "") or ""
                    is_outside_leg = (an_src.lower() == "outside" or an_dst.lower() == "outside")
                    return bool(is_outside_leg)
                except Exception:
                    return False

            def dest_matches_asset(tx):
                if not asset_filter:
                    return True
                return ((getattr(tx, "asset_type_destination", "") or "").lower() == asset_filter)

            def src_matches_asset(tx):
                if not asset_filter:
                    return True
                if ((getattr(tx, "asset_type_source", "") or "").lower() == asset_filter):
                    return True
                # Legacy fallback: treat certain transfers as Non‑Liquid on source side
                return _legacy_non_liquid_src(tx)

            def amt_in(tx):
                if (
                    getattr(tx, "destination_amount", None) is not None
                    and getattr(tx, "account_destination", None)
                    and getattr(tx.account_destination, "currency", None)
                ):
                    return convert_to_base(
                        tx.destination_amount or Decimal("0"),
                        tx.account_destination.currency,
                        request=self.request,
                        user=self.request.user,
                    )
                return convert_to_base(
                    tx.amount or Decimal("0"),
                    tx.currency,
                    request=self.request,
                    user=self.request.user,
                )

            def amt_out(tx):
                return convert_to_base(
                    tx.amount or Decimal("0"),
                    tx.currency,
                    request=self.request,
                    user=self.request.user,
                )

            def _is_outside(acct) -> bool:
                try:
                    if not acct:
                        return False
                    name = (getattr(acct, "account_name", "") or "").strip().lower()
                    typ = (getattr(acct, "account_type", "") or "").strip().lower()
                    return name == "outside" or typ == "outside"
                except Exception:
                    return False

            for tx in obj_list:
                try:
                    added = False
                    subbed = False
                    ttype_l = (getattr(tx, "transaction_type", "") or "").lower()
                    dest_is_outside = _is_outside(getattr(tx, "account_destination", None))
                    src_is_outside = _is_outside(getattr(tx, "account_source", None))
                    if acc_any and ent_any:
                        # Pair scope: only count when both sides match on the same side
                        if (
                            str(tx.account_destination_id) == str(acc_any)
                            and str(tx.entity_destination_id) == str(ent_any)
                        ) and dest_matches_asset(tx):
                            # For liquid totals, exclude transfers to Outside from inflow
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and dest_is_outside):
                                total += amt_in(tx)
                            added = True
                        if (
                            str(tx.account_source_id) == str(acc_any)
                            and str(tx.entity_source_id) == str(ent_any)
                        ) and src_matches_asset(tx):
                            # For liquid totals, exclude transfers from Outside from outflow
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and src_is_outside):
                                total -= amt_out(tx)
                            subbed = True
                    elif acc_any:
                        if str(tx.account_destination_id) == str(acc_any) and dest_matches_asset(tx):
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and dest_is_outside):
                                total += amt_in(tx); added = True
                        if str(tx.account_source_id) == str(acc_any) and src_matches_asset(tx):
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and src_is_outside):
                                total -= amt_out(tx); subbed = True
                    elif ent_any:
                        if str(tx.entity_destination_id) == str(ent_any) and dest_matches_asset(tx):
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and dest_is_outside):
                                total += amt_in(tx); added = True
                        if str(tx.entity_source_id) == str(ent_any) and src_matches_asset(tx):
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and src_is_outside):
                                total -= amt_out(tx); subbed = True
                    else:
                        # Fallback: general rule over the visible subset
                        if dest_matches_asset(tx):
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and dest_is_outside):
                                total += amt_in(tx)
                        if src_matches_asset(tx):
                            if not (asset_filter == "liquid" and ttype_l == "transfer" and src_is_outside):
                                total -= amt_out(tx)
                except Exception:
                    continue
            ctx["summary_total"] = total
        else:
            ctx["summary_total"] = None
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("bulk-action")
        selected_ids = request.POST.getlist("selected_ids")

        if action == "delete" and selected_ids:
            qs = Transaction.objects.filter(
                user=request.user, id__in=selected_ids, is_reversal=False
            )
            warned = False
            deleted = 0
            blocked = 0
            # Validate deletions won't cause overdrafts; delete safe ones only
            from .services import validate_delete_no_future_negative_balances
            # Build a set of IDs to exclude as we plan deletions within this batch
            excluded_batch = set()
            for txn in qs.order_by("date", "id"):
                try:
                    validate_delete_no_future_negative_balances(
                        txn, excluded_ids=excluded_batch, for_update=False
                    )
                except Exception:
                    blocked += 1
                    continue
                # Safe to delete: add to exclusion set and perform reversal+hide
                excluded_batch.add(txn.id)
                _reverse_and_hide(txn, actor=request.user)
                deleted += 1
                if txn.transaction_type == "loan_disbursement":
                    loan = getattr(txn, "loan_disbursement", None)
                    if loan:
                        loan.delete()
                        warned = True
            if warned:
                messages.warning(
                    request,
                    "Deleting a loan disbursement also removes the associated loan.",
                )
            if deleted:
                messages.success(request, f"{deleted} transaction(s) deleted.")
                # Persist inline undo for last processed deleted txn (best-effort)
                last_txn = (
                    Transaction.all_objects.filter(user=request.user)
                    .order_by("-id")
                    .first()
                )
                if last_txn:
                    request.session["undo_txn_id"] = last_txn.pk
                    request.session["undo_txn_desc"] = last_txn.description
            if blocked:
                messages.error(
                    request,
                    f"{blocked} transaction(s) were blocked because deletion would overdraw future balances.",
                )

        return redirect(reverse("transactions:transaction_list"))


def bulk_action(request):
    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_ids")

        if selected_ids:

            qs = Transaction.objects.filter(
                user=request.user, pk__in=selected_ids, is_reversal=False
            )
            warned = False
            deleted = 0
            blocked = 0
            from .services import validate_delete_no_future_negative_balances
            excluded_batch = set()
            for txn in qs.order_by("date", "id"):
                try:
                    validate_delete_no_future_negative_balances(
                        txn, excluded_ids=excluded_batch, for_update=False
                    )
                except Exception:
                    blocked += 1
                    continue
                excluded_batch.add(txn.id)
                _reverse_and_hide(txn, actor=request.user)
                deleted += 1
                if txn.transaction_type == "loan_disbursement":
                    loan = getattr(txn, "loan_disbursement", None)
                    if loan:
                        loan.delete()
                        warned = True
            if warned:
                messages.warning(
                    request,
                    "Deleting a loan disbursement also removes the associated loan.",
                )
            if deleted:
                messages.success(request, f"{deleted} transaction(s) deleted.")
                last_txn = (
                    Transaction.all_objects.filter(user=request.user)
                    .order_by("-id")
                    .first()
                )
                if last_txn:
                    request.session["undo_txn_id"] = last_txn.pk
                    request.session["undo_txn_desc"] = last_txn.description
            if blocked:
                messages.error(
                    request,
                    f"{blocked} transaction(s) were blocked because deletion would overdraw future balances.",
                )
        return redirect(reverse("transactions:transaction_list"))

    return redirect(reverse("transactions:transaction_list"))


class TransactionCreateView(CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    def get_initial(self):
        initial = super().get_initial()
        for fld in [
            "transaction_type",
            "account_source",
            "account_destination",
            "entity_source",
            "entity_destination",
            # allow prefill from links
            "date",
            "description",
        ]:
            val = self.request.GET.get(fld)
            if val:
                initial[fld] = val
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = TransactionTemplate.objects.filter(user=self.request.user)
        templates_json_dict = {t.id: t.autopop_map or {} for t in templates}
        context["templates_json"] = json.dumps(templates_json_dict)
        accounts = Account.objects.filter(
            user=self.request.user, is_active=True, system_hidden=False
        )
        account_map = {a.id: (a.currency.code if a.currency else "") for a in accounts}
        context["account_currency_map"] = json.dumps(account_map)
        from .constants import ENTITY_SIDE_BY_TX

        context["entity_side_map"] = json.dumps(ENTITY_SIDE_BY_TX)
        context["quick_account_form"] = AccountForm(show_actions=False)
        context["quick_entity_form"] = EntityForm(show_actions=False)
        context["selected_txn_type"] = self.request.POST.get(
            "transaction_type"
        ) or context["form"].initial.get("transaction_type")
        context["loan_id"] = self.request.GET.get("loan") or self.request.POST.get(
            "loan_id"
        )
        tx_type = context["selected_txn_type"] or ""
        context["show_balance_summary"] = not (
            tx_type == "income" or tx_type.startswith("sell")
        )
        return context

    def form_valid(self, form):
        loan_id = self.request.POST.get("loan_id")
        loan = None
        if loan_id:
            loan = get_object_or_404(Loan, pk=loan_id, user=self.request.user)

        form.instance.user = self.request.user
        visible_tx = form.save(commit=False)
        visible_tx.user = self.request.user

        src_acc = visible_tx.account_source
        dest_acc = visible_tx.account_destination
        dest_amt = form.cleaned_data.get("destination_amount")
        if (
            (visible_tx.transaction_type or "").lower() == "transfer"
            and src_acc
            and dest_acc
            and src_acc.currency_id != dest_acc.currency_id
        ):
            src_amount = visible_tx.amount
            if not dest_amt:
                dest_amt = convert_amount(
                    src_amount, src_acc.currency, dest_acc.currency
                )

            with transaction.atomic():
                # Ensure the parent uses the source account currency so child
                # legs' currencies make sense (tests expect parent.currency == src)
                visible_tx.currency = src_acc.currency
                visible_tx.destination_amount = dest_amt
                visible_tx.save()
                form.save_categories(visible_tx)

                # Use Remittance entity/account to fully populate child legs
                rem_ent = ensure_remittance_entity(self.request.user)
                rem_acc = ensure_remittance_account(self.request.user)

                # Debit: source -> remittance (source currency)
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=src_amount,
                    account_source=src_acc,
                    account_destination=rem_acc,
                    entity_source=visible_tx.entity_source,
                    entity_destination=rem_ent,
                    parent_transfer=visible_tx,
                    currency=src_acc.currency,
                    is_hidden=True,
                )

                # Credit: remittance -> destination (dest currency)
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=dest_amt,
                    destination_amount=dest_amt,
                    account_source=rem_acc,
                    account_destination=dest_acc,
                    entity_source=rem_ent,
                    entity_destination=visible_tx.entity_destination,
                    parent_transfer=visible_tx,
                    currency=dest_acc.currency,
                    is_hidden=True,
                )
            self.object = visible_tx
            messages.success(self.request, "Transaction saved successfully!")
            if loan:
                paid = Decimal(str(visible_tx.amount or 0))
                principal_applied = min(paid, loan.outstanding_balance)
                excess = paid - principal_applied
                loan.outstanding_balance -= principal_applied
                if excess > 0:
                    loan.interest_paid = (loan.interest_paid or Decimal("0")) + excess
                    loan.save(update_fields=["outstanding_balance", "interest_paid"])
                else:
                    loan.save(update_fields=["outstanding_balance"])
            return HttpResponseRedirect(self.get_success_url())
        else:
            self.object = form.save()
            messages.success(self.request, "Transaction saved successfully!")
            if loan:
                paid = Decimal(str(visible_tx.amount or 0))
                principal_applied = min(paid, loan.outstanding_balance)
                excess = paid - principal_applied
                loan.outstanding_balance -= principal_applied
                if excess > 0:
                    loan.interest_paid = (loan.interest_paid or Decimal("0")) + excess
                    loan.save(update_fields=["outstanding_balance", "interest_paid"])
                else:
                    loan.save(update_fields=["outstanding_balance"])
            return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        try:
            logger.error(f"Transaction form invalid: {getattr(form, 'errors', None)}")
        except Exception:
            pass
        return super().form_invalid(form)


class TransactionUpdateView(UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_edit_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    # Only truly read-only transaction types (no edits allowed at all)
    READ_ONLY_TYPES = {
        "loan_disbursement",
        "loan_repayment",
    }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        # Make financial fields read-only in Edit; use Correct for amount changes
        kwargs["disable_amount"] = True
        return kwargs

    def get_queryset(self):
        # Only allow editing of currently visible, non-reversed transactions
        return (
            super()
            .get_queryset()
            .filter(user=self.request.user, is_reversal=False)
            .exclude(description__istartswith="reversal of")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = TransactionTemplate.objects.filter(user=self.request.user)
        templates_json_dict = {t.id: t.autopop_map or {} for t in templates}
        context["templates_json"] = json.dumps(templates_json_dict)
        accounts = Account.objects.filter(
            user=self.request.user, is_active=True, system_hidden=False
        )
        account_map = {a.id: (a.currency.code if a.currency else "") for a in accounts}
        context["account_currency_map"] = json.dumps(account_map)
        from .constants import ENTITY_SIDE_BY_TX

        context["entity_side_map"] = json.dumps(ENTITY_SIDE_BY_TX)
        context["selected_txn_type"] = self.request.POST.get(
            "transaction_type"
        ) or context["form"].initial.get("transaction_type")
        tx_type = context["selected_txn_type"] or ""
        context["show_balance_summary"] = not (
            tx_type == "income" or tx_type.startswith("sell")
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        tx_type = (self.object.transaction_type or "").lower()
        # If this is a truly read-only type, disable all fields
        if tx_type in self.READ_ONLY_TYPES:
            for field in form.fields.values():
                field.disabled = True
        # If this is an acquisition-related transaction, disable only the
        # transaction_type field so users can edit description/date/amount/
        # remarks. The acquisition model controls linked legs and deletion
        # flows so transaction_type must remain immutable in the form.
        elif (
            tx_type in ("buy acquisition", "sell acquisition")
            or getattr(self.object, "acquisition_purchase", None)
            or getattr(self.object, "acquisition_sale", None)
        ):
            for name, field in form.fields.items():
                try:
                    if name == "transaction_type":
                        field.disabled = True
                except Exception:
                    pass
        return form

    def form_valid(self, form):
        visible_tx = form.save(commit=False)
        # Ensure description changes from POST are preserved even when
        # some fields are disabled in the form.
        try:
            if "description" in form.cleaned_data and form.cleaned_data["description"]:
                visible_tx.description = form.cleaned_data["description"]
        except Exception:
            pass
        # Defensive guard: if the form disabled amount fields (edit flows),
        # preserve the instance's amounts rather than trusting POST data.
        try:
            if form.fields.get("amount") and getattr(
                form.fields["amount"], "disabled", False
            ):
                visible_tx.amount = getattr(self.object, "amount", visible_tx.amount)
        except Exception:
            pass
        try:
            if form.fields.get("destination_amount") and getattr(
                form.fields["destination_amount"], "disabled", False
            ):
                visible_tx.destination_amount = getattr(
                    self.object, "destination_amount", visible_tx.destination_amount
                )
        except Exception:
            pass
        src_acc = visible_tx.account_source
        dest_acc = visible_tx.account_destination
        dest_amt = form.cleaned_data.get("destination_amount")
        is_cross = (
            (visible_tx.transaction_type or "").lower() == "transfer"
            and src_acc
            and dest_acc
            and src_acc.currency_id != dest_acc.currency_id
        )
        with transaction.atomic():
            Transaction.all_objects.filter(parent_transfer=visible_tx).delete()
            if is_cross:
                src_amount = visible_tx.amount
                if not dest_amt:
                    dest_amt = convert_amount(
                        src_amount, src_acc.currency, dest_acc.currency
                    )

                # Ensure parent currency matches source account
                visible_tx.currency = src_acc.currency
                visible_tx.destination_amount = dest_amt
                # Persist description first in case later operations depend on it
                try:
                    if "description" in form.cleaned_data and form.cleaned_data["description"]:
                        visible_tx.description = form.cleaned_data["description"]
                except Exception:
                    pass
                visible_tx.save()
                # Use the same form instance to persist category selection
                form.save_categories(visible_tx)

                rem_ent = ensure_remittance_entity(self.request.user)
                rem_acc = ensure_remittance_account(self.request.user)

                # Source account debit to Remittance (source currency)
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=src_amount,
                    account_source=src_acc,
                    account_destination=rem_acc,
                    entity_source=visible_tx.entity_source,
                    entity_destination=rem_ent,
                    parent_transfer=visible_tx,
                    currency=src_acc.currency,
                    is_hidden=True,
                )

                # Remittance credit to destination account (dest currency)
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=dest_amt,
                    destination_amount=dest_amt,
                    account_source=rem_acc,
                    account_destination=dest_acc,
                    entity_source=rem_ent,
                    entity_destination=visible_tx.entity_destination,
                    parent_transfer=visible_tx,
                    currency=dest_acc.currency,
                    is_hidden=True,
                )
            else:
                try:
                    if "description" in form.cleaned_data and form.cleaned_data["description"]:
                        visible_tx.description = form.cleaned_data["description"]
                except Exception:
                    pass
                visible_tx.save()
                form.save_categories(visible_tx)

        # Fallback: ensure category from POST is persisted even if the form
        # scoping/filtering prevented the ModelChoiceField from validating.
        try:
            raw_cat = self.request.POST.get("category")
            if raw_cat:
                from transactions.models import CategoryTag

                cid = int(raw_cat)
                tag = CategoryTag.objects.filter(pk=cid, user=self.request.user).first()
                if tag:
                    visible_tx.categories.set([tag])
        except Exception:
            # Don't block the save on fallback errors
            pass
        # Defensive persist: if the form provided a CategoryTag in cleaned_data,
        # ensure it is attached to the transaction. This covers cases where
        # client-side scoping may have filtered the select and the raw POST
        # matched a valid tag id.
        try:
            cat = getattr(form, "cleaned_data", {}).get("category")
            if cat:
                visible_tx.categories.set([cat])
        except Exception:
            pass
        self.object = visible_tx
        messages.success(self.request, "Transaction updated successfully!")
        # Final safeguard: ensure description from POST is persisted even if
        # subsequent operations (e.g., category saves) or disabled-field logic
        # caused it to be lost. Update directly if provided.
        try:
            desc_post = (self.request.POST.get("description") or "").strip()
            if desc_post and desc_post != (visible_tx.description or ""):
                Transaction.all_objects.filter(pk=visible_tx.pk).update(description=desc_post)
                visible_tx.description = desc_post
        except Exception:
            pass
        # If this transaction is linked to an Acquisition (purchase or sale),
        # return the user to the Acquisition detail page so they see the
        # acquisition context after editing buy/sell/capital rows.
        try:
            acq = getattr(visible_tx, "acquisition_purchase", None) or getattr(
                visible_tx, "acquisition_sale", None
            )
            if acq:
                return HttpResponseRedirect(reverse("acquisitions:acquisition-detail", args=[acq.pk]))
        except Exception:
            # If anything goes wrong resolving the acquisition, fall back to
            # the normal transactions list redirect.
            pass
        # Additionally, handle legacy capital-return rows that are not
        # explicitly linked to an Acquisition. Detect the pattern and
        # redirect to the matching acquisition when possible.
        try:
            tx_type_l = (visible_tx.transaction_type or "").lower()
            looks_like_capital = False
            if tx_type_l in {"sell acquisition", "sell_acquisition"}:
                looks_like_capital = True
            else:
                # Pattern: a transfer from Outside back to the same entity
                # typically represents a capital return when accompanied by
                # a sale. Use this as a heuristic.
                if (
                    tx_type_l == "transfer"
                    and getattr(visible_tx, "account_source", None)
                    and getattr(visible_tx.account_source, "account_name", None) == "Outside"
                    and getattr(visible_tx, "entity_source_id", None)
                    and getattr(visible_tx, "entity_destination_id", None)
                    and visible_tx.entity_source_id == visible_tx.entity_destination_id
                ):
                    looks_like_capital = True
            if looks_like_capital:
                from acquisitions.models import Acquisition
                desc = (visible_tx.description or "").strip()
                q = Acquisition.objects.filter(user=self.request.user)
                if desc:
                    q = q.filter(name__icontains=desc.split(" ")[1] if " " in desc else desc)
                # Further narrow by matching purchase amount to this row's amount
                q = q.filter(purchase_tx__amount=visible_tx.amount)
                acq2 = q.order_by("-id").first()
                if acq2:
                    return HttpResponseRedirect(reverse("acquisitions:acquisition-detail", args=[acq2.pk]))
        except Exception:
            pass
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Block POSTs only for truly read-only transaction types. Acquisition
        # related transactions may be edited (fields except transaction_type)
        # via the transaction edit UI; however, prevent changing transaction
        # type on update and disallow direct deletion of acquisition legs
        # that belong to an Acquisition with multiple legs (handled by the
        # Acquisition delete UI).
        if (self.object.transaction_type or "").lower() in self.READ_ONLY_TYPES:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()
        # Otherwise allow POST to proceed and handle immutables in form_valid
        return super().post(request, *args, **kwargs)


class TransactionCorrectView(UpdateView):
    """Immutable correction flow: reverse original and create a replacement.

    Renders a form similar to the edit view, but on submit it uses the
    correction service to validate forward balances and create a new
    replacement row while hiding/reversing the original.
    """
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_correct_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    READ_ONLY_TYPES = {
        "loan_disbursement",
        "loan_repayment",
    }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        # In correction mode, amounts should be editable by default.
        kwargs["disable_amount"] = False
        # Hide default Save/Cancel; we render a dedicated Apply Correction button
        kwargs["show_actions"] = False
        return kwargs

    def get_queryset(self):
        # Only allow correcting currently visible, non-reversal rows
        return (
            super()
            .get_queryset()
            .filter(user=self.request.user, is_reversal=False)
            .exclude(description__istartswith="reversal of")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        templates = TransactionTemplate.objects.filter(user=self.request.user)
        templates_json_dict = {t.id: t.autopop_map or {} for t in templates}
        ctx["templates_json"] = json.dumps(templates_json_dict)
        accounts = Account.objects.filter(
            user=self.request.user, is_active=True, system_hidden=False
        )
        account_map = {a.id: (a.currency.code if a.currency else "") for a in accounts}
        ctx["account_currency_map"] = json.dumps(account_map)
        from .constants import ENTITY_SIDE_BY_TX

        ctx["entity_side_map"] = json.dumps(ENTITY_SIDE_BY_TX)
        ctx["selected_txn_type"] = self.request.POST.get(
            "transaction_type"
        ) or ctx["form"].initial.get("transaction_type")
        tx_type = ctx["selected_txn_type"] or ""
        ctx["show_balance_summary"] = not (
            tx_type == "income" or tx_type.startswith("sell")
        )
        ctx["correct_mode"] = True
        # If a pocket-minimum hint was captured during POST validation, expose it to the template
        try:
            hint = getattr(self, "_pocket_minimum_hint", None)
            if hint:
                ctx["pocket_minimum_hint"] = hint
        except Exception:
            pass
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Block correction for truly read-only types
        if (self.object.transaction_type or "").lower() in self.READ_ONLY_TYPES:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied()

        form = self.get_form()
        if not form.is_valid():
            messages.error(self.request, "Please correct the errors below.")
            return self.form_invalid(form)

        original = self.object
        cleaned = form.cleaned_data
        src_acc = cleaned.get("account_source")
        dest_acc = cleaned.get("account_destination")
        tx_type = (cleaned.get("transaction_type") or "").lower()
        dest_amt = cleaned.get("destination_amount")

        # Build replacement data for the parent row
        new_data = {
            "user": request.user,
            "date": cleaned.get("date") or original.date,
            "description": cleaned.get("description") or original.description,
            "transaction_type": cleaned.get("transaction_type") or original.transaction_type,
            "amount": cleaned.get("amount"),
            "account_source": src_acc,
            "account_destination": dest_acc,
            "entity_source": cleaned.get("entity_source"),
            "entity_destination": cleaned.get("entity_destination"),
            # currency inferred below
        }

        is_cross = (
            tx_type == "transfer"
            and src_acc
            and dest_acc
            and src_acc.currency_id != dest_acc.currency_id
        )
        if is_cross:
            # Parent uses source account currency; carry destination_amount
            new_data["currency"] = src_acc.currency
            new_data["destination_amount"] = dest_amt
        else:
            # Ensure currency is supplied for model validation. Mirror the
            # TransactionForm.save() derivation rules so full_clean() in the
            # correction service doesn't fail on a blank currency.
            cur = None
            try:
                if (tx_type or "").lower() == "income" and dest_acc and getattr(dest_acc, "currency", None):
                    cur = dest_acc.currency
                elif src_acc and getattr(src_acc, "currency", None):
                    cur = src_acc.currency
                elif dest_acc and getattr(dest_acc, "currency", None):
                    cur = dest_acc.currency
                else:
                    # Fallback to the user's base currency when available
                    cur = getattr(request.user, "base_currency", None)
            except Exception:
                cur = None
            if cur is not None:
                new_data["currency"] = cur

        # Perform correction (validates and reverses original atomically)
        from .services import correct_transaction

        try:
            replacement = correct_transaction(original, new_data, actor=request.user)
        except Exception as e:
            # Surface a user-friendly message when balances would go negative
            from django.core.exceptions import ValidationError

            if isinstance(e, ValidationError):
                # Attach the error to the form so it appears inline under the field
                try:
                    message_dict = getattr(e, "message_dict", None)
                    if isinstance(message_dict, dict):
                        for field, msgs in message_dict.items():
                            if isinstance(msgs, (list, tuple)) and msgs:
                                form.add_error(field, msgs[0])
                            else:
                                form.add_error(None, str(msgs))
                    else:
                        form.add_error(None, getattr(e, "message", str(e)))
                except Exception:
                    form.add_error(None, str(e))

                # If this is the pocket-minimum error, add a small inline hint to the context
                try:
                    min_amt = getattr(e, "suggest_correction_min_amount", None)
                    code = getattr(e, "currency_code", "")
                    if min_amt:
                        from decimal import Decimal as _D
                        self._pocket_minimum_hint = {
                            "amount": _D(str(min_amt)),
                            "currency_code": code or "",
                        }
                except Exception:
                    pass
                return self.form_invalid(form)
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        # Persist selected category on the replacement
        try:
            form.save_categories(replacement)
        except Exception:
            pass

        # For cross-currency transfers, create hidden child legs mirroring create/update flows
        if is_cross:
            from accounts.utils import ensure_remittance_account
            from entities.utils import ensure_remittance_entity

            rem_ent = ensure_remittance_entity(self.request.user)
            rem_acc = ensure_remittance_account(self.request.user)
            src_amount = cleaned.get("amount")
            dest_amount = dest_amt
            # Create child legs hidden under the new parent
            Transaction.all_objects.create(
                user=self.request.user,
                date=replacement.date,
                description=replacement.description,
                transaction_type="transfer",
                amount=src_amount,
                account_source=src_acc,
                account_destination=rem_acc,
                entity_source=replacement.entity_source,
                entity_destination=rem_ent,
                parent_transfer=replacement,
                currency=src_acc.currency,
                is_hidden=True,
            )
            Transaction.all_objects.create(
                user=self.request.user,
                date=replacement.date,
                description=replacement.description,
                transaction_type="transfer",
                amount=dest_amount,
                destination_amount=dest_amount,
                account_source=rem_acc,
                account_destination=dest_acc,
                entity_source=rem_ent,
                entity_destination=replacement.entity_destination,
                parent_transfer=replacement,
                currency=dest_acc.currency,
                is_hidden=True,
            )

        messages.success(self.request, "Correction applied successfully!")
        # Redirect to acquisition detail when applicable (same as UpdateView)
        try:
            acq = getattr(replacement, "acquisition_purchase", None) or getattr(
                replacement, "acquisition_sale", None
            )
            if acq:
                return HttpResponseRedirect(reverse("acquisitions:acquisition-detail", args=[acq.pk]))
        except Exception:
            pass
        return HttpResponseRedirect(self.get_success_url())


def transaction_delete(request, pk):
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    # If this transaction is linked to an Acquisition, ensure we don't allow
    # deleting only one leg when the Acquisition has multiple linked
    # transactions (purchase + capital return / profit). Deleting a single
    # leg would leave the Acquisition inconsistent; require using the
    # Acquisition delete flow which handles reversing both legs.
    try:
        acq_purchase = getattr(txn, "acquisition_purchase", None)
        acq_sale = getattr(txn, "acquisition_sale", None)
        acq = acq_purchase or acq_sale
        if acq:
            # Count how many acquisition-related txns are present (purchase and sell)
            legs = 0
            if acq.purchase_tx_id:
                legs += 1
            if acq.sell_tx_id:
                legs += 1
            # If there are multiple legs, disallow deleting just one via
            # the transactions UI to avoid partial removal.
            if legs > 1:
                messages.error(
                    request,
                    "Cannot delete a single acquisition transaction when the acquisition has multiple linked transactions. Use the Acquisition Delete action to remove the acquisition and its transactions."
                )
                return redirect(reverse("acquisitions:acquisition-detail", args=[acq.pk]))
    except Exception:
        # On any error during this check, fall back to existing behavior.
        pass
    # Prevent deletions that would create negative future balances
    try:
        from .services import validate_delete_no_future_negative_balances

        validate_delete_no_future_negative_balances(txn, for_update=False)
    except Exception as e:
        from django.core.exceptions import ValidationError

        if isinstance(e, ValidationError):
            messages.error(
                request,
                getattr(e, "message", None)
                or "; ".join(
                    [
                        f"{k}: {', '.join(map(str, v))}" if isinstance(v, (list, tuple)) else str(v)
                        for k, v in getattr(e, "message_dict", {"error": [str(e)]}).items()
                    ]
                ),
            )
            return redirect(reverse("transactions:transaction_list"))
    # Perform reversal/hide BEFORE deleting the loan so the reversal can
    # reference the original safely; the subsequent loan.delete() will then
    # remove the original and set the reversal's reversed_transaction to NULL
    # via on_delete=SET_NULL.
    _reverse_and_hide(txn, actor=request.user)
    if txn.transaction_type == "loan_disbursement":
        loan = getattr(txn, "loan_disbursement", None)
        if loan:
            loan.delete()
            messages.warning(
                request,
                "Deleting a loan disbursement also removes the associated loan.",
            )
    undo_url = reverse("transactions:transaction_undo_delete", args=[txn.pk])
    messages.success(
        request,
        "Transaction deleted. "
        + f'<a href="{undo_url}" class="ms-2 btn btn-sm btn-light">Undo</a>',
        extra_tags="safe",
    )
    request.session["undo_txn_id"] = txn.pk
    request.session["undo_txn_desc"] = txn.description
    # No additional hints
    return redirect(reverse("transactions:transaction_list"))


# ------------- templates --------------------


class TemplateListView(TemplateDropdownMixin, ListView):
    model = TransactionTemplate
    template_name = "transactions/template_list.html"

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class TemplateCreateView(TemplateDropdownMixin, CreateView):
    model = TransactionTemplate
    form_class = TemplateForm
    template_name = "transactions/template_form.html"
    success_url = reverse_lazy("transactions:template_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["quick_account_form"] = AccountForm(show_actions=False)
        ctx["quick_entity_form"] = EntityForm(show_actions=False)
        ctx["selected_txn_type"] = self.request.POST.get("transaction_type") or ctx[
            "form"
        ].initial.get("transaction_type")
        return ctx

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Template saved successfully!")
        return response


class TemplateUpdateView(TemplateDropdownMixin, UpdateView):
    model = TransactionTemplate
    form_class = TemplateForm
    template_name = "transactions/template_form.html"
    success_url = reverse_lazy("transactions:template_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["quick_account_form"] = AccountForm(show_actions=False)
        ctx["quick_entity_form"] = EntityForm(show_actions=False)
        ctx["selected_txn_type"] = self.request.POST.get("transaction_type") or ctx[
            "form"
        ].initial.get("transaction_type")
        return ctx

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Template updated successfully!")
        return response


class TemplateDeleteView(DeleteView):
    model = TransactionTemplate
    template_name = "transactions/template_confirm_delete.html"
    success_url = reverse_lazy("transactions:template_list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Template deleted.")
        return super().delete(request, *args, **kwargs)


@require_POST
def api_create_template(request):
    """Create a transaction template via AJAX."""
    form = TemplateForm(request.POST, user=request.user)
    if form.is_valid():
        tpl = form.save(commit=False)
        tpl.user = request.user
        tpl.save()
        return JsonResponse({"id": tpl.pk, "name": tpl.name})
    return JsonResponse({"errors": form.errors}, status=400)


@require_GET
def pair_balance(request):
    """Return aggregate balance for a specific account and entity pair."""
    account_id = request.GET.get("account")
    entity_id = request.GET.get("entity")
    if not account_id or not entity_id:
        return JsonResponse({"error": "missing parameters"}, status=400)
    try:
        acc_id = int(account_id)
        ent_id = int(entity_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid id(s)"}, status=400)

    try:
        balance = get_account_entity_balance(acc_id, ent_id, user=request.user)
        account = (
            Account.objects.filter(pk=acc_id).select_related("currency").first()
        )
    except Exception as e:
        # Log and attempt a simpler fallback computation to avoid breaking the UI
        logger.exception("pair_balance primary computation failed")
        from transactions.models import Transaction
        try:
            amount_expr = Case(
                When(destination_amount__isnull=False, then=F("destination_amount")),
                default=F("amount"),
                output_field=DecimalField(),
            )
            inflow = (
                Transaction.objects.filter(
                    parent_transfer__isnull=True,
                    user=request.user,
                    account_destination_id=acc_id,
                    entity_destination_id=ent_id,
                    asset_type_destination__iexact="liquid",
                )
                .aggregate(total=Sum(amount_expr))
                .get("total")
                or Decimal("0")
            )
            outflow = (
                Transaction.objects.filter(
                    parent_transfer__isnull=True,
                    user=request.user,
                    account_source_id=acc_id,
                    entity_source_id=ent_id,
                    asset_type_source__iexact="liquid",
                )
                .aggregate(total=Sum("amount"))
                .get("total")
                or Decimal("0")
            )
            balance = inflow - outflow
            account = (
                Account.objects.filter(pk=acc_id).select_related("currency").first()
            )
        except Exception as e2:
            logger.exception("pair_balance fallback computation failed")
            return JsonResponse({"error": str(e2)}, status=500)
    base_code = (
        account.currency.code
        if account and account.currency
        else (
            request.user.base_currency.code
            if getattr(request.user, "base_currency_id", None)
            else "PHP"
        )
    )
    cur_code = base_code
    if request.GET.get("convert"):
        active = get_active_currency(request)
        if active and active.code != base_code:
            balance = convert_amount(balance, base_code, active.code)
            cur_code = active.code
    # Optional fallback: if pair balance is zero or negative (no or net-outflow
    # entity-specific ledger), show the account's current balance so the user
    # sees currently available funds in the selected account.
    try:
        enable_fallback = request.GET.get("fallback", "1") != "0"
    except Exception:
        enable_fallback = True
    pair_bal = Decimal(str(balance or 0))
    if enable_fallback and pair_bal <= 0:
        try:
            acct_bal = get_account_balance(acc_id, user=request.user)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        acct_code = base_code
        if request.GET.get("convert"):
            active = get_active_currency(request)
            if active and active.code != base_code:
                acct_bal = convert_amount(acct_bal, base_code, active.code)
                acct_code = active.code
        return JsonResponse(
            {"balance": str(acct_bal), "currency": acct_code, "fallback": True}
        )

    # Optional debug output: include contributing transactions and computed sides
    if request.GET.get("debug") == "1":
        rows = []
        qs = (
            Transaction.objects.filter(
                parent_transfer__isnull=True,
                user=request.user,
            )
            .filter(
                Q(entity_destination_id=ent_id, account_destination_id=acc_id)
                | Q(entity_source_id=ent_id, account_source_id=acc_id)
            )
            .select_related(
                "account_source",
                "account_destination",
                "currency",
                "account_destination__currency",
            )
            .order_by("date", "id")
        )
        running = Decimal("0")
        for t in qs:
            side = None
            amt = None
            if (
                t.account_destination_id == acc_id
                and t.entity_destination_id == ent_id
                and (t.asset_type_destination or "").lower() == "liquid"
            ):
                side = "+dest"
                amt = t.destination_amount if t.destination_amount is not None else t.amount
                running += Decimal(str(amt or 0))
            if (
                t.account_source_id == acc_id
                and t.entity_source_id == ent_id
                and (t.asset_type_source or "").lower() == "liquid"
            ):
                side = "-src"
                amt = t.amount
                running -= Decimal(str(amt or 0))
            rows.append(
                {
                    "id": t.id,
                    "date": t.date.isoformat() if getattr(t, "date", None) else None,
                    "type": t.transaction_type,
                    "desc": t.description,
                    "side": side,
                    "amount": str(amt) if amt is not None else None,
                    "dest_amount": str(t.destination_amount) if t.destination_amount is not None else None,
                    "asset_src": t.asset_type_source,
                    "asset_dst": t.asset_type_destination,
                    "is_hidden": t.is_hidden,
                    "is_reversal": t.is_reversal,
                    "parent_transfer": t.parent_transfer_id,
                }
            )
        return JsonResponse(
            {
                "balance": str(balance),
                "currency": cur_code,
                "fallback": False,
                "items": rows,
            }
        )

    return JsonResponse({"balance": str(balance), "currency": cur_code, "fallback": False})


@require_GET
def account_balance(request, pk):
    """Return balance for a single account."""
    bal = get_account_balance(pk, user=request.user)
    account = Account.objects.filter(pk=pk).select_related("currency").first()
    base_code = (
        account.currency.code
        if account and account.currency
        else (
            request.user.base_currency.code
            if getattr(request.user, "base_currency_id", None)
            else "PHP"
        )
    )
    cur_code = base_code
    if request.GET.get("convert"):
        active = get_active_currency(request)
        if active and active.code != base_code:
            bal = convert_amount(bal, base_code, active.code)
            cur_code = active.code
    return JsonResponse({"balance": str(bal), "currency": cur_code})


@require_GET
def entity_balance(request, pk):
    """Return balance for a single entity."""
    bal = util_entity_balance(pk, user=request.user)
    base_code = (
        request.user.base_currency.code
        if getattr(request.user, "base_currency_id", None)
        else "PHP"
    )
    cur_code = base_code
    if request.GET.get("convert"):
        active = get_active_currency(request)
        if active and active.code != base_code:
            bal = convert_amount(bal, base_code, active.code)
            cur_code = active.code
    return JsonResponse({"balance": str(bal), "currency": cur_code})


@require_GET
def tag_list(request):
    tx_type = request.GET.get("transaction_type")
    ent = request.GET.get("entity")
    # Debug: log incoming params to help diagnose missing tags in UI
    try:
        logger.debug(
            f"tag_list called with transaction_type={tx_type!r}, entity={ent!r}, user_id={getattr(request.user, 'id', None)}"
        )
    except Exception:
        # Avoid raising in production if logging fails for any reason
        pass
    # Only include tags owned by the user. If no entity is provided,
    # return an empty list so the client knows to require selecting an entity first.
    tags = CategoryTag.objects.filter(user=request.user)
    # If no entity provided, respond with an empty list (manager page enforces entity selection).
    if not ent:
        return JsonResponse([], safe=False)
    # If a specific type is provided, filter by it. When omitted (on manager
    # page with 'all'), return all types for that entity.
    # Deeper diagnostics: log counts to help understand why client sees no tags.
    try:
        total_for_user = CategoryTag.objects.filter(user=request.user).count()
        count_for_entity = CategoryTag.objects.filter(
            user=request.user, entity_id=ent
        ).count()
        logger.debug(
            f"tag_list diagnostics: total_for_user={total_for_user}, count_for_entity={count_for_entity}"
        )
    except Exception:
        # Don't fail if counting/logging fails
        total_for_user = None
        count_for_entity = None

    if tx_type and tx_type.lower() != "all":
        # Normalize incoming type and support both underscore/space variants
        tx_norm = tx_type.strip()
        tx_key = tx_norm.replace(" ", "_").lower()

        # Consult central CATEGORY_SCOPE_BY_TX mapping when available
        scope = CATEGORY_SCOPE_BY_TX.get(tx_key)
        if scope:
            # If a fixed_name is requested, filter by name (case-insensitive)
            fixed = scope.get("fixed_name")
            if fixed:
                # Match tags whose name equals the fixed label (case-insensitive)
                tags = tags.filter(name__iexact=fixed)
            else:
                cat_tx = scope.get("category_tx") or tx_key
                # Accept either underscore or space variants for stored transaction_type
                alt = (
                    cat_tx.replace("_", " ")
                    if "_" in cat_tx
                    else cat_tx.replace(" ", "_")
                )
                # Include tags with matching type OR without a type (generic)
                tags = tags.filter(
                    Q(transaction_type__iexact=cat_tx)
                    | Q(transaction_type__iexact=alt)
                    | Q(transaction_type__isnull=True)
                    | Q(transaction_type__exact="")
                )
        else:
            # Fallback: accept both underscore and space separated forms
            alt = (
                tx_norm.replace("_", " ")
                if "_" in tx_norm
                else tx_norm.replace(" ", "_")
            )
            tags = tags.filter(
                Q(transaction_type__iexact=tx_norm)
                | Q(transaction_type__iexact=alt)
                | Q(transaction_type__isnull=True)
                | Q(transaction_type__exact="")
            )

    # Filter to the requested entity only, but include global (entity is null)
    tags = tags.filter(Q(entity_id=ent) | Q(entity__isnull=True))

    try:
        c = tags.count()
        logger.debug(
            f"tag_list matched {c} tags for transaction_type={tx_type!r} entity={ent!r}"
        )

        # Do not override explicit filters; return empty when none match.
    except Exception:
        # If tag counting fails, continue and return whatever queryset we have
        pass

    # Include transaction_type so the manager can display badges and allow an
    # overview across all types when desired.
    data = [
        {"id": t.pk, "name": t.name, "transaction_type": t.transaction_type or ""}
        for t in tags.order_by("name")
    ]
    return JsonResponse(data, safe=False)


@require_POST
def tag_create(request):
    name = request.POST.get("name", "").strip()
    tx_type = request.POST.get("transaction_type")
    ent = request.POST.get("entity") or None
    if not name:
        return JsonResponse({"error": "name"}, status=400)
    # Enforce entity scoping: tags must be created with an entity
    if not ent:
        return JsonResponse({"error": "entity required"}, status=400)
    key = CategoryTag._normalize_name(name)
    tag = CategoryTag.objects.filter(
        user=request.user,
        transaction_type=tx_type,
        name_key=key,
        entity_id=ent,
    ).first()
    if not tag:
        tag = CategoryTag.objects.create(
            user=request.user,
            transaction_type=tx_type,
            name=name,
            entity_id=ent,
        )
    return JsonResponse({"id": tag.pk, "name": tag.name})


@require_http_methods(["PATCH"])
def tag_update(request, pk):
    tag = get_object_or_404(CategoryTag, pk=pk, user=request.user)
    data = QueryDict(request.body)
    name = data.get("name", "").strip()
    if name:
        # If another tag with the same normalized key exists in the same scope,
        # merge into it instead of violating the unique constraint.
        key = CategoryTag._normalize_name(name)
        existing = (
            CategoryTag.objects.filter(
                user=request.user,
                transaction_type=tag.transaction_type,
                name_key=key,
                entity_id=tag.entity_id,
            )
            .exclude(pk=tag.pk)
            .first()
        )
        if existing:
            # Move transactions from current tag to existing one, then delete current tag
            for tx in tag.transactions.all():
                existing.transactions.add(tx)
            tag.delete()
            return JsonResponse({"id": existing.pk, "name": existing.name})
        # Otherwise, just rename
        tag.name = name
        tag.save(update_fields=["name", "name_key"])  # name_key set in save()
    return JsonResponse({"id": tag.pk, "name": tag.name})


@require_http_methods(["DELETE"])
def tag_delete(request, pk):
    tag = get_object_or_404(CategoryTag, pk=pk, user=request.user)
    # Save last-deleted tag in session for quick undo
    request.session["last_deleted_tag"] = {
        "name": tag.name,
        "transaction_type": tag.transaction_type,
        "entity_id": tag.entity_id,
    }
    tag.delete()
    return JsonResponse(
        {
            "status": "deleted",
            "undo_url": reverse("transactions:tag_undo_delete"),
        }
    )


@csrf_exempt
@require_POST
def e2e_create_test_user(request):
    """Development-only helper to create/login a test user and return session id.

    This endpoint is intentionally gated by DEBUG and a token in settings
    (`E2E_TEST_TOKEN`) to avoid exposure in production.
    """
    if not getattr(settings, "DEBUG", False):
        return JsonResponse({"error": "disabled"}, status=403)

    token = request.POST.get("token") or request.GET.get("token")
    if token != getattr(settings, "E2E_TEST_TOKEN", "devtoken"):
        return JsonResponse({"error": "bad token"}, status=403)

    username = request.POST.get("username", "testuser")
    password = request.POST.get("password", "testpass")
    email = request.POST.get("email", "test@example.com")

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=username, defaults={"email": email}
    )
    # Ensure password is set to the requested value (helpful when user already exists)
    user.set_password(password)
    user.save()

    # Log the user into this request so a session is created.
    auth_login(request, user)
    request.session.save()
    return JsonResponse({"sessionid": request.session.session_key})


@require_POST
def tag_undo_delete(request):
    data = request.session.pop("last_deleted_tag", None)
    if not data:
        return JsonResponse({"error": "nothing to undo"}, status=400)
    tag = CategoryTag.objects.create(
        user=request.user,
        name=data.get("name", ""),
        transaction_type=data.get("transaction_type"),
        entity_id=data.get("entity_id"),
    )
    return JsonResponse({"id": tag.pk, "name": tag.name})


@require_http_methods(["GET", "POST"])
def tags(request):
    if request.method == "POST":
        return tag_create(request)
    return tag_list(request)


@require_http_methods(["PATCH", "DELETE"])
def tag_detail(request, pk):
    if request.method == "PATCH":
        return tag_update(request, pk)
    return tag_delete(request, pk)


@login_required
def category_manager(request):
    entities = (
        Entity.objects.filter(
            Q(user=request.user) | Q(user__isnull=True),
            is_active=True,
            system_hidden=False,
        )
        .exclude(entity_type="outside")
        .exclude(entity_name="Outside")
    )
    return render(
        request,
        "transactions/category_manager.html",
        {"entities": entities},
    )


@require_GET
def entity_category_summary(request, entity_id):
    qs = Transaction.objects.filter(
        user=request.user,
        parent_transfer__isnull=True,
        categories__isnull=False,
    ).filter(Q(entity_source_id=entity_id) | Q(entity_destination_id=entity_id))
    amount_expr = Case(
        When(destination_amount__isnull=False, then=F("destination_amount")),
        default=F("amount"),
        output_field=DecimalField(),
    )
    data = (
        qs.values("categories__name")
        .annotate(total=Sum(amount_expr))
        .order_by("categories__name")
    )
    return JsonResponse(list(data), safe=False)
