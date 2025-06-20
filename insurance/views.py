from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from acquisitions.models import Acquisition
from entities.models import Entity
from .models import Insurance, PremiumPayment
from .forms import InsuranceForm
from transactions.forms import TransactionForm
from transactions.models import Transaction
from accounts.models import Account
from decimal import Decimal
from django.shortcuts import get_object_or_404, render, redirect


@method_decorator(login_required, name="dispatch")
class InsuranceListView(ListView):
    model = Insurance
    template_name = "insurance/insurance_list.html"

    def get_queryset(self):
        return Insurance.objects.filter(user=self.request.user).with_cash_value().with_total_premiums_paid()


@method_decorator(login_required, name="dispatch")
class InsuranceCreateView(CreateView):
    model = Insurance
    form_class = InsuranceForm
    template_name = "insurance/insurance_form.html"
    success_url = reverse_lazy("insurance:list")

    def get_initial(self):
        initial = super().get_initial()
        ent = self.request.GET.get("entity")
        if ent:
            initial["entity"] = ent
        acq = self.request.GET.get("acquisition")
        if acq:
            initial["acquisition"] = acq
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.status = "inactive"
        return super().form_valid(form)
    
    def get_success_url(self):
        if self.object.entity_id:
            return reverse("entities:detail", args=[self.object.entity_id])
        return super().get_success_url()


@method_decorator(login_required, name="dispatch")
class InsuranceDetailView(DetailView):
    model = Insurance
    template_name = "insurance/insurance_detail.html"

    def get_queryset(self):
        return (
            Insurance.objects.filter(user=self.request.user)
            .with_cash_value()
            .with_total_premiums_paid()
        )
    

@login_required
def category_list(request):
    data = [
        {"id": "personal", "label": "Personal Insurance"},
        {"id": "property", "label": "Property Insurance"},
        {"id": "vehicle", "label": "Vehicle Insurance"},
        {"id": "travel", "label": "Travel Insurance"},
    ]
    return JsonResponse(data, safe=False)


@login_required
def acquisition_options(request, entity_id, category):
    if category not in {"property", "vehicle"}:
        raise Http404()
    try:
        Entity.objects.get(pk=entity_id, user=request.user)
    except Entity.DoesNotExist:
        raise Http404()
    acqs = (
        Acquisition.objects.filter(
            user=request.user,
            purchase_tx__entity_destination_id=entity_id,
            category=category,
        )
        .values("id", "name")
        .order_by("name")
    )
    return JsonResponse(list(acqs), safe=False)


@login_required
def pay_premium(request, pk):
    insurance = get_object_or_404(Insurance, pk=pk, user=request.user)
    if request.method == "POST":
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            tx = form.save(commit=False)
            tx.user = request.user
            tx.save()
            PremiumPayment.objects.create(
                insurance=insurance,
                date=tx.date,
                amount=tx.amount or Decimal("0"),
                note=tx.description or "",
                transaction=tx,
            )
            if insurance.status != "active":
                insurance.status = "active"
                insurance.save(update_fields=["status"])
            return redirect("entities:detail", pk=insurance.entity_id)
    else:
        initial = {
            "transaction_type": "premium_payment",
            "entity_source": insurance.entity_id,
        }
        acc = Account.objects.active().filter(user=request.user).first()
        if acc:
            initial["account_source"] = acc.pk
        form = TransactionForm(initial=initial, user=request.user)
    return render(request, "insurance/pay_premium_form.html", {"form": form, "insurance": insurance})