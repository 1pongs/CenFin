from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View

from django.http import HttpResponseRedirect
from django.urls import reverse_lazy, reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
import json

from .models import Transaction, TransactionTemplate
from .forms import TransactionForm, TemplateForm
from accounts.models import Account
from entities.models import Entity
from .constants import TXN_TYPE_CHOICES, ASSET_TYPE_CHOICES

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
    context_object_name = "object_list"

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET

        tx_type = q.get("transaction_type")
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)

        acc_src = q.get("account_source")
        if acc_src:
            qs = qs.filter(account_source_id=acc_src)

        acc_dest = q.get("account_destination")
        if acc_dest:
            qs = qs.filter(account_destination_id=acc_dest)

        ent_src = q.get("entity_source")
        if ent_src:
            qs = qs.filter(entity_source_id=ent_src)

        ent_dest = q.get("entity_destination")
        if ent_dest:
            qs = qs.filter(entity_destination_id=ent_dest)

        asset_type = q.get("asset_type")
        if asset_type:
            side = q.get("asset_side", "source")
            if side == "destination":
                qs = qs.filter(asset_type_destination=asset_type)
            else:
                qs = qs.filter(asset_type_source=asset_type)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["accounts"] = Account.objects.active()
        ctx["entities"] = Entity.objects.active()
        ctx["txn_type_choices"] = TXN_TYPE_CHOICES
        ctx["asset_type_choices"] = ASSET_TYPE_CHOICES
        return ctx    

    def post(self, request, *args, **kwargs):
        # Alamin kung anong action ang na-post
        action = request.POST.get('action')
        selected_ids = request.POST.getlist('selected_ids')

        if action == "delete_multiple" and selected_ids:
            Transaction.objects.filter(pk__in=selected_ids).delete()
            messages.success(
                request,
                f"{len(selected_ids)} transaction(s) successfully deleted."
            )
        else:
            if action == "delete_multiple" and not selected_ids:
                messages.error(request, "Please select at least one transaction to delete.")
            # Kung gusto mo magdagdag ng ibang action sa future, pwede dyan

        return redirect('transactions:transaction_list')
    
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