from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib import messages


# Create your views here.

from .models import Acquisition
from .forms import AcquisitionForm, SellAcquisitionForm
from transactions.models import Transaction
from accounts.models import Account
from accounts.forms import AccountForm
from entities.models import Entity
from entities.forms import EntityForm


class AcquisitionListView(TemplateView):
    template_name = "acquisitions/acquisition_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["acquisitions"] = Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(user=self.request.user)
        return ctx


class AcquisitionCreateView(FormView):
    template_name = "acquisitions/acquisition_form.html"
    form_class = AcquisitionForm
    success_url = reverse_lazy("acquisitions:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['quick_account_form'] = AccountForm(show_actions=False)
        ctx['quick_entity_form'] = EntityForm(show_actions=False)
        return ctx
    
    def form_valid(self, form):
        data = form.cleaned_data
        tx = Transaction(
            user=self.request.user,
            date=data["date"],
            description=data["name"],
            transaction_type="buy product",
            amount=data["amount"],
            account_source=data["account_source"],
            account_destination=data["account_destination"],
            entity_source=data["entity_source"],
            entity_destination=data["entity_destination"],
            remarks=data["remarks"],
        )
        try:
            tx.full_clean()
        except ValidationError as e:
            form.add_error(None, e.message or e.messages)
            return self.form_invalid(form)
        tx.save()
        Acquisition.objects.create(
            name=data["name"],
            category=data["category"],
            purchase_tx=tx,
            current_value=data.get("current_value"),
            market=data.get("market", ""),
            is_sellable=data.get("is_sellable"),
            expected_lifespan_years=data.get("expected_lifespan_years"),
            location=data.get("location", ""),
            insurance_type=data.get("insurance_type"),
            cash_value=data.get("cash_value"),
            maturity_date=data.get("maturity_date"),
            provider=data.get("provider", ""),
            user=self.request.user,
        )
        return super().form_valid(form)

def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


def sell_acquisition(request, pk):
    acquisition = get_object_or_404(Acquisition, pk=pk, user=request.user)
    if request.method == "POST":
        form = SellAcquisitionForm(request.POST, user=request.user)
        if form.is_valid():
            data = form.cleaned_data
            buy_tx = acquisition.purchase_tx
            diff = data["sale_price"] - (buy_tx.amount or 0)
            sell_tx = Transaction.objects.create(
                user=request.user,
                date=data["date"],
                description=f"Sell {acquisition.name}",
                transaction_type="sell product",
                amount=diff,
                 account_source=data["account_source"],
                account_destination=data["account_destination"],
                entity_source=data["entity_source"],
                entity_destination=data["entity_destination"],
                remarks=data["remarks"],
            )
            acquisition.sell_tx = sell_tx
            acquisition.save()
        
            return redirect("acquisitions:list")
    else:
        initial = {
            "date": timezone.now().date(),
            "account_source": acquisition.purchase_tx.account_destination_id,
            "account_destination": acquisition.purchase_tx.account_source_id,
            "entity_source": acquisition.purchase_tx.entity_destination_id,
            "entity_destination": acquisition.purchase_tx.entity_source_id,
        }
        form = SellAcquisitionForm(initial=initial, user=request.user)
    context = {
        "form": form,
        "acquisition": acquisition,
    }
    return render(request, "acquisitions/acquisition_sell.html", context)