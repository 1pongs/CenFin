from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages

from acquisitions.models import Acquisition
from entities.models import Entity
from .models import Insurance, PremiumPayment
from .forms import InsuranceForm, PremiumPaymentForm
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
        response = super().form_valid(form)
        ins = self.object
        acq = Acquisition.objects.create(
            name=ins.policy_owner or ins.person_insured,
            category=Acquisition.CATEGORY_INSURANCE,
            user=ins.user,
            purchase_tx=None,
            status="inactive",
            sum_assured_amount=ins.sum_assured,
            insurance_type=ins.insurance_type,
            provider=ins.provider,
            maturity_date=ins.maturity_date,
        )
        ins.acquisition = acq
        ins.save(update_fields=["acquisition"])
        return response
    
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
    get_object_or_404(Entity, pk=entity_id, user=request.user)
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
        form = PremiumPaymentForm(request.POST, user=request.user)
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
            updates = []
            if insurance.status != "active":
                insurance.status = "active"
                updates.append("status")
            if insurance.acquisition and insurance.acquisition.status != "active":
                insurance.acquisition.status = "active"
                insurance.acquisition.save(update_fields=["status"])
            if updates:
                insurance.save(update_fields=updates)
            return redirect("entities:detail", pk=insurance.entity_id)
    else:
        initial = {
            "transaction_type": "premium_payment",
            "entity_source": insurance.entity_id,
        }
        acc = Account.objects.active().filter(user=request.user).first()
        if acc:
            initial["account_source"] = acc.pk
        form = PremiumPaymentForm(initial=initial, user=request.user)
    return render(request, "insurance/pay_premium_form.html", {"form": form, "insurance": insurance})


@method_decorator(login_required, name="dispatch")
class InsuranceUpdateView(UpdateView):
    model = Insurance
    form_class = InsuranceForm
    template_name = "insurance/insurance_form.html"
    success_url = reverse_lazy("insurance:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Insurance policy updated successfully!")
        return response

    def get_success_url(self):
        if self.object.entity_id:
            return reverse("entities:detail", args=[self.object.entity_id])
        return super().get_success_url()


@method_decorator(login_required, name="dispatch")
class InsuranceDeleteView(DeleteView):
    model = Insurance
    template_name = "insurance/insurance_confirm_delete.html"
    success_url = reverse_lazy("insurance:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Insurance policy deleted.")
        return super().delete(request, *args, **kwargs)

    def get_success_url(self):
        if self.object.entity_id:
            return reverse("entities:detail", args=[self.object.entity_id])
        return super().get_success_url()
