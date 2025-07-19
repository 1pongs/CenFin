from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.utils import timezone
from datetime import timedelta

from django.http import HttpResponseRedirect, JsonResponse, QueryDict
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.db.models import Sum
from django.db import transaction
from decimal import Decimal
import json
from cenfin_proj.utils import (
    get_account_entity_balance,
    get_entity_balance as util_entity_balance,
    get_account_balance,
)
from utils.currency import get_active_currency, convert_amount

from .models import Transaction, TransactionTemplate, CategoryTag
from .forms import TransactionForm, TemplateForm
from accounts.forms import AccountForm
from entities.forms import EntityForm
from accounts.models import Account
from entities.models import Entity

from .constants import TXN_TYPE_CHOICES

# Create your views here.

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
        qs = super().get_queryset().filter(user=self.request.user)
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
            Transaction.objects.filter(user=request.user, id__in=selected_ids).delete()
            messages.success(request, f"{len(selected_ids)} transaction(s) deleted.")

        return redirect(reverse("transactions:transaction_list"))
        
def bulk_action(request):
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_ids')

        if selected_ids:
                Transaction.objects.filter(user=request.user, pk__in=selected_ids).delete()
        return redirect(reverse('transactions:transaction_list'))
            
    return redirect(reverse('transactions:transaction_list'))

class TransactionCreateView(CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

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
        account_map = {a.id: a.currency.code for a in accounts}
        context['account_currency_map'] = json.dumps(account_map)
        context['quick_account_form'] = AccountForm(show_actions=False)
        context['quick_entity_form'] = EntityForm(show_actions=False)
        context['selected_txn_type'] = (
            self.request.POST.get('transaction_type') or context['form'].initial.get('transaction_type')
        )
        tx_type = context['selected_txn_type'] or ''
        context['show_balance_summary'] = not (tx_type == 'income' or tx_type.startswith('sell'))
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        self.object = form.save()
        visible_tx = self.object

        src_acc = visible_tx.account_source
        dest_acc = visible_tx.account_destination
        dest_amt = form.cleaned_data.get("destination_amount")
        if (
            (visible_tx.transaction_type or "").lower() == "transfer"
            and src_acc
            and dest_acc
            and src_acc.currency_id != dest_acc.currency_id
        ):
            from accounts.utils import get_remittance_account
            from entities.utils import ensure_remittance_entity

            remittance_entity = ensure_remittance_entity(self.request.user)
            rem_src = get_remittance_account(self.request.user, src_acc.currency)
            rem_dest = get_remittance_account(self.request.user, dest_acc.currency)

            with transaction.atomic():
                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=visible_tx.amount,
                    currency=src_acc.currency,
                    account_source=src_acc,
                    account_destination=rem_src,
                    entity_source=visible_tx.entity_source,
                    entity_destination=remittance_entity,
                    is_hidden=True,
                    parent_transfer=visible_tx,
                )

                Transaction.all_objects.create(
                    user=self.request.user,
                    date=visible_tx.date,
                    description=visible_tx.description,
                    transaction_type="transfer",
                    amount=dest_amt or visible_tx.amount,
                    currency=dest_acc.currency,
                    account_source=rem_dest,
                    account_destination=dest_acc,
                    entity_source=remittance_entity,
                    entity_destination=visible_tx.entity_destination,
                    is_hidden=True,
                    parent_transfer=visible_tx,
                )
                
        messages.success(self.request, "Transaction saved successfully!")
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
        response = super().form_valid(form)
        messages.success(self.request, "Transaction updated successfully!")
        return response

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

    txn.delete()
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
    active = get_active_currency(request)
    base_code = request.user.base_currency.code if getattr(request.user, "base_currency_id", None) else "PHP"
    if active:
        balance = convert_amount(balance, base_code, active.code, user=request.user)
        cur_code = active.code
    else:
        cur_code = base_code
    return JsonResponse({"balance": str(balance), "currency": cur_code})


@require_GET
def account_balance(request, pk):
    """Return balance for a single account."""
    bal = get_account_balance(pk, user=request.user)
    active = get_active_currency(request)
    base_code = request.user.base_currency.code if getattr(request.user, "base_currency_id", None) else "PHP"
    if active:
        bal = convert_amount(bal, base_code, active.code, user=request.user)
        cur_code = active.code
    else:
        cur_code = base_code
    return JsonResponse({"balance": str(bal), "currency": cur_code})


@require_GET
def entity_balance(request, pk):
    """Return balance for a single entity."""
    bal = util_entity_balance(pk, user=request.user)
    active = get_active_currency(request)
    base_code = request.user.base_currency.code if getattr(request.user, "base_currency_id", None) else "PHP"
    if active:
        bal = convert_amount(bal, base_code, active.code, user=request.user)
        cur_code = active.code
    else:
        cur_code = base_code
    return JsonResponse({"balance": str(bal), "currency": cur_code})


@require_GET
def tag_list(request):
    tx_type = request.GET.get("transaction_type")
    tags = CategoryTag.objects.filter(user=request.user)
    if tx_type:
        tags = tags.filter(transaction_type=tx_type)
    data = [{"id": t.pk, "name": t.name} for t in tags.order_by("name")]
    return JsonResponse(data, safe=False)


@require_POST
def tag_create(request):
    name = request.POST.get("name", "").strip()
    tx_type = request.POST.get("transaction_type")
    if not name:
        return JsonResponse({"error": "name"}, status=400)
    tag, _ = CategoryTag.objects.get_or_create(
        user=request.user,
        transaction_type=tx_type,
        name=name,
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