from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.utils import timezone
from datetime import timedelta

from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_GET
from django.db.models import Sum
from decimal import Decimal
import json

from .models import Transaction, TransactionTemplate
from .forms import TransactionForm, TemplateForm
from accounts.models import Account
from entities.models import Entity

from .constants import TXN_TYPE_CHOICES

# Create your views here.

class TemplateDropdownMixin:
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["templates"] = TransactionTemplate.objects.all()
        return ctx

# ------------- transactions -----------------
class TransactionListView(ListView):
    model = Transaction
    template_name = "transactions/transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        qs = super().get_queryset()
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
        ctx["accounts"] = Account.objects.active()
        ctx["entities"] = Entity.objects.active()
        ctx["txn_type_choices"] = TXN_TYPE_CHOICES
        params = self.request.GET
        ctx["search"] = params.get("q", "")
        ctx["sort"] = params.get("sort", "-date")
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("bulk-action")
        selected_ids = request.POST.getlist("selected_ids")

        if action == "delete" and selected_ids:
            Transaction.objects.filter(id__in=selected_ids).delete()
            messages.success(request, f"{len(selected_ids)} transaction(s) deleted.")

        return redirect(reverse("transactions:transaction_list"))
        
def bulk_action(request):
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_ids')

        if selected_ids:
                Transaction.objects.filter(pk__in=selected_ids).delete()
        return redirect(reverse('transactions:transaction_list'))
            
    return redirect(reverse('transactions:transaction_list'))

class TransactionCreateView(CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = TransactionTemplate.objects.all()
        templates_json_dict = {
            t.id: t.autopop_map or {}
            for t in templates
        }
        context['templates_json'] = json.dumps(templates_json_dict)
        return context

    def form_valid(self, form):
        response = super().form_valid(form) 
        messages.success(self.request, "Transaction saved successfully!")
        return response

class TransactionUpdateView(UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/transaction_edit_form.html"
    success_url = reverse_lazy("transactions:transaction_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        templates = TransactionTemplate.objects.all()
        templates_json_dict = {
            t.id: t.autopop_map or {}
            for t in templates
        }
        context['templates_json'] = json.dumps(templates_json_dict)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)  
        messages.success(self.request, "Transaction updated successfully!")
        return response


def transaction_delete(request, pk):
    txn = get_object_or_404(Transaction, pk=pk)

    txn.delete()
    messages.success(request, "Transaction deleted.")
    return redirect(reverse('transactions:transaction_list'))

# ------------- templates --------------------

class TemplateListView(TemplateDropdownMixin, ListView):
    model = TransactionTemplate
    template_name = "transactions/template_list.html"

class TemplateCreateView(TemplateDropdownMixin, CreateView):
    model = TransactionTemplate
    form_class = TemplateForm
    template_name = "transactions/template_form.html"
    success_url = reverse_lazy("transactions:template_list")

    def form_valid(self, form):
        response = super().form_valid(form)  
        messages.success(self.request, "Template saved successfully!")
        return response

class TemplateUpdateView(TemplateDropdownMixin, UpdateView):
    model = TransactionTemplate
    form_class = TemplateForm
    template_name = "transactions/template_form.html"
    success_url = reverse_lazy("transactions:template_list")

    def form_valid(self, form):
        response = super().form_valid(form)    
        messages.success(self.request, "Template updated successfully!")
        return response

class TemplateDeleteView(DeleteView):
    model = TransactionTemplate
    template_name = "transactions/template_confirm_delete.html"
    success_url = reverse_lazy("transactions:template_list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Template deleted.")
        return super().delete(request, *args, **kwargs)


@require_GET
def pair_balance(request):
    """Return aggregate balance for a specific account and entity pair."""
    account_id = request.GET.get("account")
    entity_id = request.GET.get("entity")
    if not account_id or not entity_id:
        return JsonResponse({"error": "missing parameters"}, status=400)

    inflow = (
        Transaction.objects.filter(
            account_destination_id=account_id,
            entity_destination_id=entity_id,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    outflow = (
        Transaction.objects.filter(
            account_source_id=account_id,
            entity_source_id=entity_id,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    balance = inflow - outflow
    return JsonResponse({"balance": str(balance)})