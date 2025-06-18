from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, FormView, ListView, DetailView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db.models import Q


# Create your views here.

from .models import Acquisition
from .forms import AcquisitionForm, SellAcquisitionForm
from transactions.models import Transaction
from accounts.models import Account
from accounts.forms import AccountForm
from entities.models import Entity
from entities.forms import EntityForm

CARD_FIELDS_BY_CATEGORY = {
    "product":    ["date_bought", "amount", "target_selling_date", "status"],
    "stock_bond": ["date_bought", "amount", "current_value", "market", "target_selling_date", "status"],
    "property":   ["date_bought", "amount", "location", "expected_lifespan_years", "is_sellable", "status"],
    "insurance":  ["date_bought", "amount", "insurance_type", "cash_value", "maturity_date", "provider", "status"],
    "equipment":  ["date_bought", "amount", "location", "expected_lifespan_years", "is_sellable", "status"],
    "vehicle":    ["date_bought", "amount", "model_year", "mileage", "plate_number", "is_sellable", "status"],
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
        qs = Acquisition.objects.select_related("purchase_tx", "sell_tx").filter(user=self.request.user)
        cat = self.request.GET.get("category")
        if cat:
            qs = qs.filter(category=cat)
        month = self.request.GET.get("month")
        if month:
            try:
                y, m = map(int, month.split("-"))
                qs = qs.filter(purchase_tx__date__year=y, purchase_tx__date__month=m)
            except ValueError:
                pass
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()
        upcoming = today + timezone.timedelta(days=30)
        ctx["urgent_qs"] = self.get_queryset().filter(target_selling_date__range=[today, upcoming], sell_tx__isnull=True)
        ctx["current_category"] = self.request.GET.get("category", "")
        ctx["current_month"] = self.request.GET.get("month", "")
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
            try:
                ent = Entity.objects.get(pk=ent_id, user=self.request.user)
                kwargs["locked_entity"] = ent
            except Entity.DoesNotExist:
                pass
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
            target_selling_date=data.get("target_selling_date"),
            mileage=data.get("mileage"),
            plate_number=data.get("plate_number", ""),
            model_year=data.get("model_year"),
            insurance_type=data.get("insurance_type"),
            cash_value=data.get("cash_value"),
            maturity_date=data.get("maturity_date"),
            provider=data.get("provider", ""),
            user=self.request.user,
        )
        return super().form_valid(form)

    def get_success_url(self):
        ent_id = self.request.GET.get("entity")
        if ent_id:
            try:
                Entity.objects.get(pk=ent_id, user=self.request.user)
                return reverse("entities:detail", args=[ent_id])
            except Entity.DoesNotExist:
                pass
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
                "target_selling_date": self.object.target_selling_date,
                "mileage": self.object.mileage,
                "plate_number": self.object.plate_number,
                "model_year": self.object.model_year,
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
        acq.target_selling_date = data.get("target_selling_date")
        acq.mileage = data.get("mileage")
        acq.plate_number = data.get("plate_number", "")
        acq.model_year = data.get("model_year")
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