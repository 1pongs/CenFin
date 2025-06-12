from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from django.utils import timezone


# Create your views here.

from .models import Asset
from .forms import AssetForm, SellAssetForm
from transactions.models import Transaction
from accounts.models import Account
from entities.models import Entity


class AssetListView(TemplateView):
    template_name = "assets/asset_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assets"] = Asset.objects.select_related("purchase_tx", "sell_tx")
        return ctx


class AssetCreateView(FormView):
    template_name = "assets/asset_form.html"
    form_class = AssetForm
    success_url = reverse_lazy("assets:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return ctx
    
    def form_valid(self, form):
        data = form.cleaned_data
        tx = Transaction.objects.create(
            date=data["date"],
            description=data["name"],
            transaction_type="buy asset",
            amount=data["amount"],
            account_source=data["account_source"],
            account_destination=data["account_destination"],
            entity_source=data["entity_source"],
            entity_destination=data["entity_destination"],
            remarks=data["remarks"],
        )
        Asset.objects.create(name=data["name"], purchase_tx=tx)
        return super().form_valid(form)


def sell_asset(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == "POST":
        form = SellAssetForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            buy_tx = asset.purchase_tx
            diff = data["sale_price"] - (buy_tx.amount or 0)
            sell_tx = Transaction.objects.create(
                date=data["date"],
                description=f"Sell {asset.name}",
                transaction_type="sell asset",
                amount=diff,
                 account_source=data["account_source"],
                account_destination=data["account_destination"],
                entity_source=data["entity_source"],
                entity_destination=data["entity_destination"],
                remarks=data["remarks"],
            )
            asset.sell_tx = sell_tx
            asset.save()
        
            return redirect("assets:list")
    else:
        initial = {
            "date": timezone.now().date(),
            "account_source": asset.purchase_tx.account_destination_id,
            "account_destination": asset.purchase_tx.account_source_id,
            "entity_source": asset.purchase_tx.entity_destination_id,
            "entity_destination": asset.purchase_tx.entity_source_id,
        }
        form = SellAssetForm(initial=initial)
    context = {
        "form": form,
        "asset": asset,
    }
    return render(request, "assets/asset_sell.html", context)