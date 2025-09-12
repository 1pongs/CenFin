from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
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
)
from utils.currency import get_active_currency, convert_amount
from core.utils.fx import convert

from .models import Transaction, TransactionTemplate, CategoryTag
from .forms import TransactionForm, TemplateForm
from accounts.forms import AccountForm
from accounts.utils import ensure_remittance_account
from entities.utils import ensure_remittance_entity
from entities.forms import EntityForm
from accounts.models import Account
from entities.models import Entity
from liabilities.models import Loan

from .constants import TXN_TYPE_CHOICES

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
        if getattr(original, "is_reversal", False) or getattr(original, "is_reversed", False):
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
            is_hidden=True,
            is_reversal=True,
            reversed_transaction=original,
        )
        if original is txn:
            rev_parent = rev
        # mark original as reversed
        original.is_reversed = True
        original.reversed_at = timezone.now()
        if actor is not None:
            original.reversed_by = actor
        original.ledger_status = "reversed"
        original.save(update_fields=["is_reversed", "reversed_at", "reversed_by", "ledger_status"])

    Transaction.all_objects.filter(Q(pk=txn.pk) | Q(parent_transfer=txn)).update(is_hidden=True)


@login_required
def transaction_undo_delete(request, pk):
    """Undo a prior delete by un-hiding the original and removing reversals.

    We only allow undo for the given transaction id that was previously
    reversed-and-hidden by our delete flow.
    """
    original = get_object_or_404(
        Transaction.all_objects, pk=pk, user=request.user
    )
    # Identify the original and any hidden child legs
    related = [original] + list(Transaction.all_objects.filter(parent_transfer=original))
    # Ensure these were actually reversed/hidden
    if not all(getattr(t, "is_hidden", False) for t in related):
        messages.info(request, "Nothing to undo.")
        return redirect(reverse("transactions:transaction_list"))

    # Delete reversal rows for each related original
    Transaction.all_objects.filter(reversed_transaction__in=[t.pk for t in related]).delete()

    # Unhide originals and clear reversed flags
    for t in related:
        t.is_hidden = False
        t.is_reversed = False
        t.reversed_at = None
        t.reversed_by = None
        t.ledger_status = "posted"
        t.save(update_fields=["is_hidden", "is_reversed", "reversed_at", "reversed_by", "ledger_status"])

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
        archived = params.get("archived") in {"1", "true", "True"}
        if archived:
            qs = (
                Transaction.all_objects
                .filter(user=self.request.user)
                .select_related("currency")
                .filter(is_hidden=True, parent_transfer__isnull=True)
            )
        else:
            qs = (
                super()
                .get_queryset()
                .filter(user=self.request.user)
                .select_related("currency")
            )
        # Do not display reversal entries in the list
        qs = qs.filter(is_reversal=False).exclude(description__istartswith="reversal of")
        params = self.request.GET

        # Pair filter: when both account and entity are provided, show
        # transactions involving that specific pair in either direction.
        pair_account = params.get("account")
        pair_entity = params.get("entity")
        if pair_account and pair_entity:
            qs = qs.filter(
                Q(account_source_id=pair_account, entity_source_id=pair_entity)
                | Q(account_destination_id=pair_account, entity_destination_id=pair_entity)
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

        acc_src = params.get("account_source")
        if acc_src:
            qs = qs.filter(account_source_id=acc_src)

        acc_dest = params.get("account_destination")
        if acc_dest:
            qs = qs.filter(account_destination_id=acc_dest)

        ent_src = params.get("entity_source")
        if ent_src:
            qs = qs.filter(entity_source_id=ent_src)

        ent_dest = params.get("entity_destination")
        if ent_dest:
            qs = qs.filter(entity_destination_id=ent_dest)

        date_range = params.get("date_range")
        today = timezone.now().date()
        if date_range == "last7":
            qs = qs.filter(date__gte=today - timedelta(days=7))
        elif date_range == "last30":
            qs = qs.filter(date__gte=today - timedelta(days=30))
        elif date_range == "month":
            qs = qs.filter(date__year=today.year, date__month=today.month)

        return qs.order_by(sort)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        active = get_active_currency(self.request)
        disp_code = active.code if active else settings.BASE_CURRENCY
                
        ctx["display_currency"] = disp_code
        ctx["accounts"] = Account.objects.active().filter(user=self.request.user)
        ctx["entities"] = Entity.objects.active().filter(user=self.request.user)
        ctx["txn_type_choices"] = TXN_TYPE_CHOICES
        params = self.request.GET
        ctx["search"] = params.get("q", "")
        ctx["sort"] = params.get("sort", "-date")
        ctx["is_archived_view"] = params.get("archived") in {"1", "true", "True"}

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
                undo_restore_url = reverse("transactions:transaction_undo_delete", args=[undo_txn_id])
            except Exception:
                undo_restore_url = None
        ctx["undo_txn_desc"] = undo_txn_desc
        ctx["undo_restore_url"] = undo_restore_url
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("bulk-action")
        selected_ids = request.POST.getlist("selected_ids")

        if action == "delete" and selected_ids:
            qs = Transaction.objects.filter(user=request.user, id__in=selected_ids, is_reversal=False)
            warned = False
            for txn in qs:
                # First create reversal entries and hide the original
                _reverse_and_hide(txn, actor=request.user)
                # Then, if this was a loan disbursement, remove the associated loan
                # (after reversal to avoid FK errors on reversed_transaction)
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
            messages.success(request, f"{len(selected_ids)} transaction(s) deleted.")
            # Persist inline undo for last processed txn (best-effort)
            last_txn = qs.order_by("-id").first()
            if last_txn:
                request.session["undo_txn_id"] = last_txn.pk
                request.session["undo_txn_desc"] = last_txn.description

        return redirect(reverse("transactions:transaction_list"))
        
def bulk_action(request):
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_ids')

        if selected_ids:

            qs = Transaction.objects.filter(user=request.user, pk__in=selected_ids, is_reversal=False)
            warned = False
            for txn in qs:
                # Reverse first to ensure original exists when creating reversal rows
                _reverse_and_hide(txn, actor=request.user)
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
            messages.success(request, f"{len(selected_ids)} transaction(s) deleted.")
            last_txn = qs.order_by("-id").first()
            if last_txn:
                request.session["undo_txn_id"] = last_txn.pk
                request.session["undo_txn_desc"] = last_txn.description
        return redirect(reverse('transactions:transaction_list'))
            
    return redirect(reverse('transactions:transaction_list'))

class TransactionCreateView(CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    def get_initial(self):
        initial = super().get_initial()
        for fld in ["transaction_type", "account_source", "account_destination", "entity_source", "entity_destination"]:
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
        templates_json_dict = {
            t.id: t.autopop_map or {}
            for t in templates
        }
        context['templates_json'] = json.dumps(templates_json_dict)
        accounts = Account.objects.filter(user=self.request.user, is_active=True, system_hidden=False)
        account_map = {a.id: (a.currency.code if a.currency else '') for a in accounts}
        context['account_currency_map'] = json.dumps(account_map)
        context['quick_account_form'] = AccountForm(show_actions=False)
        context['quick_entity_form'] = EntityForm(show_actions=False)
        context['selected_txn_type'] = (
            self.request.POST.get('transaction_type') or context['form'].initial.get('transaction_type')
        )
        context['loan_id'] = self.request.GET.get('loan') or self.request.POST.get('loan_id')
        tx_type = context['selected_txn_type'] or ''
        context['show_balance_summary'] = not (tx_type == 'income' or tx_type.startswith('sell'))
        return context

    def form_valid(self, form):
        loan_id = self.request.POST.get('loan_id')
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
                dest_amt = convert_amount(src_amount, src_acc.currency, dest_acc.currency)

            with transaction.atomic():
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
        return super().form_invalid(form)

class TransactionUpdateView(UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_edit_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    READ_ONLY_TYPES = {
        "loan_disbursement",
        "loan_repayment",
        "buy acquisition",
        "sell acquisition",
    }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = TransactionTemplate.objects.filter(user=self.request.user)
        templates_json_dict = {
            t.id: t.autopop_map or {}
            for t in templates
        }
        context['templates_json'] = json.dumps(templates_json_dict)
        accounts = Account.objects.filter(user=self.request.user, is_active=True, system_hidden=False)
        account_map = {a.id: (a.currency.code if a.currency else '') for a in accounts}
        context['account_currency_map'] = json.dumps(account_map)
        context['selected_txn_type'] = (
            self.request.POST.get('transaction_type') or context['form'].initial.get('transaction_type')
        )
        tx_type = context['selected_txn_type'] or ''
        context['show_balance_summary'] = not (tx_type == 'income' or tx_type.startswith('sell'))
        return context
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if self.object.transaction_type in self.READ_ONLY_TYPES:
            for field in form.fields.values():
                field.disabled = True
        return form

    def form_valid(self, form):
        visible_tx = form.save(commit=False)
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
                    dest_amt = convert_amount(src_amount, src_acc.currency, dest_acc.currency)

                visible_tx.destination_amount = dest_amt
                visible_tx.save()
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
                visible_tx.save()
                form.save_categories(visible_tx)
        self.object = visible_tx
        messages.success(self.request, "Transaction updated successfully!")
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)
    
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.transaction_type in self.READ_ONLY_TYPES:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied()
        return super().post(request, *args, **kwargs)

def transaction_delete(request, pk):
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    if txn.transaction_type == "loan_disbursement":
        loan = getattr(txn, "loan_disbursement", None)
        if loan:
            loan.delete()
            messages.warning(
                request,
                "Deleting a loan disbursement also removes the associated loan.",
            )
    _reverse_and_hide(txn, actor=request.user)
    undo_url = reverse('transactions:transaction_undo_delete', args=[txn.pk])
    messages.success(request, "Transaction deleted. "+ f"<a href=\"{undo_url}\" class=\"ms-2 btn btn-sm btn-light\">Undo</a>", extra_tags="safe")
    request.session["undo_txn_id"] = txn.pk
    request.session["undo_txn_desc"] = txn.description
    return redirect(reverse('transactions:transaction_list'))

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
        ctx['quick_account_form'] = AccountForm(show_actions=False)
        ctx['quick_entity_form'] = EntityForm(show_actions=False)
        ctx['selected_txn_type'] = (
            self.request.POST.get('transaction_type') or ctx['form'].initial.get('transaction_type')
        )
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
        ctx['quick_account_form'] = AccountForm(show_actions=False)
        ctx['quick_entity_form'] = EntityForm(show_actions=False)
        ctx['selected_txn_type'] = (
            self.request.POST.get('transaction_type') or ctx['form'].initial.get('transaction_type')
        )
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

    balance = get_account_entity_balance(account_id, entity_id, user=request.user)
    account = Account.objects.filter(pk=account_id).select_related("currency").first()
    base_code = (
        account.currency.code
        if account and account.currency
        else request.user.base_currency.code
        if getattr(request.user, "base_currency_id", None)
        else "PHP"
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
        acct_bal = get_account_balance(account_id, user=request.user)
        acct_code = base_code
        if request.GET.get("convert"):
            active = get_active_currency(request)
            if active and active.code != base_code:
                acct_bal = convert_amount(acct_bal, base_code, active.code)
                acct_code = active.code
        return JsonResponse({"balance": str(acct_bal), "currency": acct_code, "fallback": True})

    return JsonResponse({"balance": str(balance), "currency": cur_code, "fallback": False})


@require_GET
def account_balance(request, pk):
    """Return balance for a single account."""
    bal = get_account_balance(pk, user=request.user)
    account = Account.objects.filter(pk=pk).select_related("currency").first()
    base_code = (
        account.currency.code
        if account and account.currency
        else request.user.base_currency.code
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
    tags = CategoryTag.objects.filter(user=request.user)
    # If a specific type is provided, filter by it. When omitted, return all types.
    if tx_type and tx_type.lower() != "all":
        tags = tags.filter(transaction_type=tx_type)
    if ent:
        tags = tags.filter(Q(entity_id=ent) | Q(entity__isnull=True))
    else:
        tags = tags.filter(entity__isnull=True)
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
    key = CategoryTag._normalize_name(name)
    tag = (
        CategoryTag.objects.filter(
            user=request.user,
            transaction_type=tx_type,
            name_key=key,
            entity_id=ent,
        ).first()
    )
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
        existing = CategoryTag.objects.filter(
            user=request.user,
            transaction_type=tag.transaction_type,
            name_key=key,
            entity_id=tag.entity_id,
        ).exclude(pk=tag.pk).first()
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
    return JsonResponse({
        "status": "deleted",
        "undo_url": reverse("transactions:tag_undo_delete"),
    })


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
    entities = Entity.objects.filter(
        Q(user=request.user) | Q(user__isnull=True),
        is_active=True,
        system_hidden=False,
    ).exclude(entity_type="outside").exclude(entity_name="Outside")
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
