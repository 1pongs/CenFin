from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

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
from entities.forms import EntityForm
from accounts.models import Account
from entities.models import Entity
from liabilities.models import Loan

from .constants import TXN_TYPE_CHOICES

# Create your views here.


def _reverse_and_hide(txn):
    """Create reversal entry/entries for a transaction then hide the original."""
    related = [txn] + list(Transaction.all_objects.filter(parent_transfer=txn))
    rev_parent = None
    for original in related:
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
            is_hidden=original.is_hidden,
        )
        if original is txn:
            rev_parent = rev

    Transaction.all_objects.filter(Q(pk=txn.pk) | Q(parent_transfer=txn)).update(is_hidden=True)

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
        qs = (
            super()
            .get_queryset()
            .filter(user=self.request.user)
            .select_related("currency")
        )
        params = self.request.GET

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
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("bulk-action")
        selected_ids = request.POST.getlist("selected_ids")

        if action == "delete" and selected_ids:
            qs = Transaction.objects.filter(user=request.user, id__in=selected_ids)
            warned = False
            for txn in qs:
                if txn.transaction_type == "loan_disbursement":
                    loan = getattr(txn, "loan_disbursement", None)
                    if loan:
                        loan.delete()
                        warned = True
                _reverse_and_hide(txn)
            if warned:
                messages.warning(
                    request,
                    "Deleting a loan disbursement also removes the associated loan.",
                )
            messages.success(request, f"{len(selected_ids)} transaction(s) deleted.")

        return redirect(reverse("transactions:transaction_list"))
        
def bulk_action(request):
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_ids')

        if selected_ids:

            qs = Transaction.objects.filter(user=request.user, pk__in=selected_ids)
            warned = False
            for txn in qs:
                if txn.transaction_type == "loan_disbursement":
                    loan = getattr(txn, "loan_disbursement", None)
                    if loan:
                        loan.delete()
                        warned = True
                _reverse_and_hide(txn)
            if warned:
                messages.warning(
                    request,
                    "Deleting a loan disbursement also removes the associated loan.",
                )
            messages.success(request, f"{len(selected_ids)} transaction(s) deleted.")
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
            if form.cleaned_data.get('amount') > loan.outstanding_balance:
                form.add_error('amount', "Payment amount cannot exceed current balance")
                return self.form_invalid(form)

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

                # Record debit from the source account in its base currency
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=src_amount,
                    account_source=src_acc,
                    entity_source=visible_tx.entity_source,
                    parent_transfer=visible_tx,
                    currency=src_acc.currency,
                    is_hidden=True,
                )

                # Record credit to the destination account in its base currency
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=dest_amt,
                    destination_amount=dest_amt,
                    account_destination=dest_acc,
                    entity_destination=visible_tx.entity_destination,
                    parent_transfer=visible_tx,
                    currency=dest_acc.currency,
                    is_hidden=True,
                )
            self.object = visible_tx
            messages.success(self.request, "Transaction saved successfully!")
            if loan:
                loan.outstanding_balance -= visible_tx.amount
                loan.save(update_fields=["outstanding_balance"])
            return HttpResponseRedirect(self.get_success_url())
        else:
            self.object = form.save()
            messages.success(self.request, "Transaction saved successfully!")
            if loan:
                loan.outstanding_balance -= visible_tx.amount
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

                # Source account debit
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=src_amount,
                    account_source=src_acc,
                    entity_source=visible_tx.entity_source,
                    parent_transfer=visible_tx,
                    currency=src_acc.currency,
                    is_hidden=True,
                )

                # Destination account credit
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=dest_amt,
                    destination_amount=dest_amt,
                    account_destination=dest_acc,
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
    _reverse_and_hide(txn)
    messages.success(request, "Transaction deleted.")
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
    return JsonResponse({"balance": str(balance), "currency": cur_code})


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
    if tx_type:
        tags = tags.filter(transaction_type=tx_type)
    if ent:
        tags = tags.filter(Q(entity_id=ent) | Q(entity__isnull=True))
    else:
        tags = tags.filter(entity__isnull=True)
    data = [{"id": t.pk, "name": t.name} for t in tags.order_by("name")]
    return JsonResponse(data, safe=False)


@require_POST
def tag_create(request):
    name = request.POST.get("name", "").strip()
    tx_type = request.POST.get("transaction_type")
    ent = request.POST.get("entity") or None
    if not name:
        return JsonResponse({"error": "name"}, status=400)
    tag, _ = CategoryTag.objects.get_or_create(
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
        tag.name = name
        tag.save(update_fields=["name"])
    return JsonResponse({"id": tag.pk, "name": tag.name})


@require_http_methods(["DELETE"])
def tag_delete(request, pk):
    tag = get_object_or_404(CategoryTag, pk=pk, user=request.user)
    tag.delete()
    return JsonResponse({"status": "deleted"})


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