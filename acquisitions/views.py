from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, FormView, ListView, DetailView, UpdateView, DeleteView
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


class AcquisitionListView(ListView):
    model = Acquisition
    template_name = "acquisitions/acquisition_list.html"
    context_object_name = "acquisitions"

    def get_queryset(self):
        return Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(user=self.request.user)


class AcquisitionCreateView(FormView):
    template_name = "acquisitions/acquisition_form.html"
    form_class = AcquisitionForm
    success_url = reverse_lazy("acquisitions:acquisition-list")

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


class AcquisitionDetailView(DetailView):
    model = Acquisition
    template_name = "acquisitions/acquisition_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("purchase_tx", "sell_tx").filter(user=self.request.user)


class AcquisitionUpdateView(AcquisitionCreateView):
    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(Acquisition, pk=kwargs["pk"], user=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("GET", "HEAD"):
            tx = self.object.purchase_tx
            kwargs["initial"] = {
                "name": self.object.name,
                "category": self.object.category,
                "date": tx.date,
                "amount": tx.amount,
                "account_source": tx.account_source_id,
                "account_destination": tx.account_destination_id,
                "entity_source": tx.entity_source_id,
                "entity_destination": tx.entity_destination_id,
                "remarks": tx.remarks,
                "current_value": self.object.current_value,
                "market": self.object.market,
                "is_sellable": self.object.is_sellable,
                "expected_lifespan_years": self.object.expected_lifespan_years,
                "location": self.object.location,
                "insurance_type": self.object.insurance_type,
                "cash_value": self.object.cash_value,
                "maturity_date": self.object.maturity_date,
                "provider": self.object.provider,
            }
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        tx = self.object.purchase_tx
        tx.date = data["date"]
        tx.description = data["name"]
        tx.amount = data["amount"]
        tx.account_source = data["account_source"]
        tx.account_destination = data["account_destination"]
        tx.entity_source = data["entity_source"]
        tx.entity_destination = data["entity_destination"]
        tx.remarks = data["remarks"]
        try:
            tx.full_clean()
        except ValidationError as e:
            form.add_error(None, e.message or e.messages)
            return self.form_invalid(form)
        tx.save()
        acq = self.object
        acq.name = data["name"]
        acq.category = data["category"]
        acq.current_value = data.get("current_value")
        acq.market = data.get("market", "")
        acq.is_sellable = data.get("is_sellable")
        acq.expected_lifespan_years = data.get("expected_lifespan_years")
        acq.location = data.get("location", "")
        acq.insurance_type = data.get("insurance_type")
        acq.cash_value = data.get("cash_value")
        acq.maturity_date = data.get("maturity_date")
        acq.provider = data.get("provider", "")
        acq.save()
        messages.success(self.request, "Acquisition updated.")
        return super().form_valid(form)


class AcquisitionDeleteView(DeleteView):
    model = Acquisition
    template_name = "acquisitions/acquisition_confirm_delete.html"
    success_url = reverse_lazy("acquisitions:acquisition-list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Acquisition deleted.")
        return super().delete(request, *args, **kwargs)


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
        
            return redirect("acquisitions:acquisition-list")
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