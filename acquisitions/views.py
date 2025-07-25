from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, FormView, ListView, DetailView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from decimal import Decimal


# Create your views here.

from .models import Acquisition
from .forms import AcquisitionForm, SellAcquisitionForm
from transactions.models import Transaction
from currencies.models import Currency
from accounts.models import Account
from accounts.forms import AccountForm
from entities.models import Entity
from entities.forms import EntityForm

CARD_FIELDS_BY_CATEGORY = {
    "product":    ["date_bought", "amount", "target_selling_date", "status"],
    "stock_bond": ["date_bought", "amount", "current_value", "market", "target_selling_date", "status"],
    "property":   ["date_bought", "amount", "location", "expected_lifespan_years", "status"],
    "insurance":  ["date_bought", "amount", "insurance_type", "cash_value", "maturity_date", "provider", "status"],
    "equipment":  ["date_bought", "amount", "location", "expected_lifespan_years", "status"],
    "vehicle":    ["date_bought", "amount", "model_year", "mileage", "plate_number", "status"],
}

# Short list of fields shown directly on the acquisition cards
CARD_SUMMARY_FIELDS_BY_CATEGORY = {
    "product":    ["date_bought", "amount", "status"],
    "stock_bond": ["date_bought", "amount", "status"],
    "property":   ["location", "date_bought", "amount", "status"],
    "insurance":  ["date_bought", "amount", "status"],
    "equipment":  ["location", "date_bought", "amount", "status"],
    "vehicle":    ["date_bought", "amount", "status"],
}

class AcquisitionListView(ListView):
    model = Acquisition
    template_name = "acquisitions/acquisition_list.html"
    context_object_name = "acquisitions"

    def get_queryset(self):
        qs = (
            Acquisition.objects.select_related("purchase_tx", "sell_tx")
            .filter(user=self.request.user)
        )
        
        qs = qs.exclude(category=Acquisition.CATEGORY_INSURANCE)

        cat = self.request.GET.get("category")
        if cat:
            qs = qs.filter(category=cat)

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        
        status = self.request.GET.get("status")
        if status == "active":
            qs = qs.filter(sell_tx__isnull=True)
        elif status == "not_active":
            qs = qs.filter(sell_tx__isnull=False)

        start = self.request.GET.get("start")
        end = self.request.GET.get("end")
        if start:
            try:
                start_date = timezone.datetime.fromisoformat(start).date()
                qs = qs.filter(purchase_tx__date__gte=start_date)
            except ValueError:
                pass
        if end:
            try:
                end_date = timezone.datetime.fromisoformat(end).date()
                qs = qs.filter(purchase_tx__date__lte=end_date)
            except ValueError:
                pass

        ent = self.request.GET.get("entity")
        if ent:
            qs = qs.filter(purchase_tx__entity_destination_id=ent)

        sort = self.request.GET.get("sort", "name")
        if sort == "balance":
            qs = qs.order_by("-purchase_tx__amount")
        elif sort == "date":
            qs = qs.order_by("-purchase_tx__date")
        else:
            qs = qs.order_by("name")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_category"] = self.request.GET.get("category", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["start"] = self.request.GET.get("start", "")
        ctx["end"] = self.request.GET.get("end", "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["sort"] = self.request.GET.get("sort", "name")
        ctx["entity_id"] = self.request.GET.get("entity", "")
        ctx["form"] = AcquisitionForm(user=self.request.user)
        ctx["form"] = AcquisitionForm(user=self.request.user)
        ctx["CARD_FIELDS_BY_CATEGORY"] = CARD_FIELDS_BY_CATEGORY
        ctx["entities"] = (
            Entity.objects.filter(
                Q(user=self.request.user) | Q(user__isnull=True),
                is_active=True,
                is_visible=True,
            )
            .exclude(entity_name="Outside")
            .order_by("entity_name")
        )
        return ctx


class AcquisitionCreateView(FormView):
    template_name = "acquisitions/acquisition_form.html"
    form_class = AcquisitionForm
    success_url = reverse_lazy("acquisitions:acquisition-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        ent_id = self.request.GET.get("entity")
        if ent_id:
            ent = get_object_or_404(Entity, pk=ent_id, user=self.request.user)
            kwargs["locked_entity"] = ent
        cat = self.request.GET.get("category")
        if cat:
            kwargs.setdefault("initial", {})["category"] = cat
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
            transaction_type="buy acquisition",
            amount=data["amount"],
            currency=data["currency"],
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
            status="active",
            current_value=data.get("current_value"),
            market=data.get("market", ""),
            expected_lifespan_years=data.get("expected_lifespan_years"),
            location=data.get("location", ""),
            target_selling_date=data.get("target_selling_date"),
            mileage=data.get("mileage"),
            plate_number=data.get("plate_number", ""),
            model_year=data.get("model_year"),
            insurance_type=data.get("insurance_type"),
            sum_assured_amount=data.get("sum_assured_amount"),
            cash_value=data.get("cash_value"),
            maturity_date=data.get("maturity_date"),
            provider=data.get("provider", ""),
            user=self.request.user,
        )
        return super().form_valid(form)

    def get_success_url(self):
        ent_id = self.request.GET.get("entity")
        if ent_id:
            get_object_or_404(Entity, pk=ent_id, user=self.request.user)
            return reverse("entities:detail", args=[ent_id])
        return super().get_success_url()

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
            initial = {
                "name": self.object.name,
                "category": self.object.category,
                "current_value": self.object.current_value,
                "market": self.object.market,
                "expected_lifespan_years": self.object.expected_lifespan_years,
                "location": self.object.location,
                "target_selling_date": self.object.target_selling_date,
                "mileage": self.object.mileage,
                "plate_number": self.object.plate_number,
                "model_year": self.object.model_year,
                "insurance_type": self.object.insurance_type,
                "sum_assured_amount": self.object.sum_assured_amount,
                "cash_value": self.object.cash_value,
                "maturity_date": self.object.maturity_date,
                "provider": self.object.provider,
            }
            if tx:
                initial.update(
                    {
                        "date": tx.date,
                        "amount": tx.amount,
                        "currency": tx.currency_id,
                        "account_source": tx.account_source_id,
                        "account_destination": tx.account_destination_id,
                        "entity_source": tx.entity_source_id,
                        "entity_destination": tx.entity_destination_id,
                        "remarks": tx.remarks,
                    }
                )
            kwargs["initial"] = initial
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        tx = self.object.purchase_tx
        creating_tx = False
        if tx is None:
            tx = Transaction(user=self.request.user, transaction_type="buy acquisition")
            creating_tx = True
            
        tx.date = data["date"]
        tx.description = data["name"]
        tx.amount = data["amount"]
        tx.currency = data["currency"]
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
        if creating_tx:
            self.object.purchase_tx = tx
        acq = self.object
        acq.name = data["name"]
        acq.category = data["category"]
        acq.current_value = data.get("current_value")
        acq.market = data.get("market", "")
        acq.expected_lifespan_years = data.get("expected_lifespan_years")
        acq.location = data.get("location", "")
        acq.target_selling_date = data.get("target_selling_date")
        acq.mileage = data.get("mileage")
        acq.plate_number = data.get("plate_number", "")
        acq.model_year = data.get("model_year")
        acq.insurance_type = data.get("insurance_type")
        acq.sum_assured_amount = data.get("sum_assured_amount")
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
            capital_cost = buy_tx.amount or Decimal("0")
            profit_amt = data["sale_price"] - capital_cost
            with transaction.atomic():
                profit_tx = Transaction.objects.create(
                    user=request.user,
                    date=data["date"],
                    description=f"Sell {acquisition.name} \u2014 profit",
                    transaction_type="sell acquisition",
                    amount=profit_amt,
                    currency=buy_tx.currency,
                    account_source=data["account_source"],
                    account_destination=data["account_destination"],
                    entity_source=data["entity_source"],
                    entity_destination=data["entity_destination"],
                    remarks=data["remarks"],
                )
                Transaction.objects.create(
                    user=request.user,
                    date=data["date"],
                    description=f"Sell {acquisition.name} \u2014 capital return",
                    transaction_type="transfer",
                    amount=capital_cost,
                    currency=buy_tx.currency,
                    account_source=data["account_source"],
                    account_destination=data["account_destination"],
                    entity_source=data["entity_source"],
                    entity_destination=data["entity_destination"],
                    remarks=data["remarks"],
                )
                acquisition.sell_tx = profit_tx
                acquisition.save()
        
            return redirect("acquisitions:acquisition-list")
    else:
        try:
            outside_acc = Account.objects.get(account_name="Outside", user__isnull=True)
            src_id = outside_acc.pk
        except Account.DoesNotExist:
            src_id = None
        initial = {
            "date": timezone.now().date(),
            "account_source": src_id,
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