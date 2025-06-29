from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView
from django.core.paginator import Paginator
from django.utils import timezone
from django.urls import reverse_lazy, reverse
from django.contrib import messages

from .models import Loan, CreditCard, Lender
from .forms import LoanForm, CreditCardForm
from django.db import transaction

class LiabilityListView(TemplateView):
    template_name = "liabilities/liability_list.html"

    def get_queryset(self, tab):
        params = self.request.GET
        search = params.get("q", "").strip()
        status = params.get("status", "")
        start = params.get("start", "")
        end = params.get("end", "")
        ent = params.get("entity")
        sort = params.get("sort", "name")

        if tab == "loans":
            qs = Loan.objects.filter(user=self.request.user)
            if search:
                qs = qs.filter(lender__name__icontains=search)
            if status == "active":
                qs = qs.filter(outstanding_balance__gt=0)
            elif status == "inactive":
                qs = qs.filter(outstanding_balance__lte=0)
            if start:
                try:
                    start_date = timezone.datetime.fromisoformat(start).date()
                    qs = qs.filter(received_date__gte=start_date)
                except ValueError:
                    pass
            if end:
                try:
                    end_date = timezone.datetime.fromisoformat(end).date()
                    qs = qs.filter(received_date__lte=end_date)
                except ValueError:
                    pass
            if ent:
                qs = qs.filter(lender_id=ent)
            if sort == "balance":
                qs = qs.order_by("-outstanding_balance")
            elif sort == "date":
                qs = qs.order_by("-received_date")
            else:
                qs = qs.order_by("lender__name")
        else:
            qs = CreditCard.objects.filter(user=self.request.user)
            if search:
                qs = qs.filter(card_name__icontains=search)
            if status == "active":
                qs = qs.filter(current_balance__gt=0)
            elif status == "inactive":
                qs = qs.filter(current_balance__lte=0)
            if start:
                try:
                    start_date = timezone.datetime.fromisoformat(start).date()
                    qs = qs.filter(created_at__date__gte=start_date)
                except ValueError:
                    pass
            if end:
                try:
                    end_date = timezone.datetime.fromisoformat(end).date()
                    qs = qs.filter(created_at__date__lte=end_date)
                except ValueError:
                    pass
            if ent:
                qs = qs.filter(issuer_id=ent)
            if sort == "balance":
                qs = qs.order_by("-current_balance")
            elif sort == "date":
                qs = qs.order_by("-created_at")
            else:
                qs = qs.order_by("card_name")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tab = self.request.GET.get("tab", "credit")
        qs = self.get_queryset(tab)
        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        ctx.update({
            "tab": tab,
            "object_list": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "credit_cards": page_obj.object_list if tab == "credit" else [],
            "loans": page_obj.object_list if tab == "loans" else [],
            "search": self.request.GET.get("q", ""),
            "status": self.request.GET.get("status", ""),
            "start": self.request.GET.get("start", ""),
            "end": self.request.GET.get("end", ""),
            "entity_id": self.request.GET.get("entity", ""),
            "sort": self.request.GET.get("sort", "name"),
            "entities": Lender.objects.all().order_by("name"),
        })
        return ctx
    
class CreditCardCreateView(CreateView):
    model = CreditCard
    form_class = CreditCardForm
    template_name = "liabilities/credit_form.html"
    success_url = reverse_lazy("liabilities:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        issuer_name = self.request.POST.get("issuer_name", "").strip()
        if form.cleaned_data.get("issuer") is None and issuer_name:
            with transaction.atomic():
                issuer, _ = Lender.objects.get_or_create(name=issuer_name)
            form.instance.issuer = issuer
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cancel = self.request.GET.get("next") or reverse("liabilities:list")
        kwargs["cancel_url"] = cancel
        return kwargs


class LoanCreateView(CreateView):
    model = Loan
    form_class = LoanForm
    template_name = "liabilities/loan_form.html"
    success_url = reverse_lazy("liabilities:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        lender_name = self.request.POST.get("lender_name", "").strip()
        if form.cleaned_data.get("lender") is None and lender_name:
            with transaction.atomic():
                lender, _ = Lender.objects.get_or_create(name=lender_name)
            form.instance.lender = lender
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cancel = self.request.GET.get("next") or reverse("liabilities:list")
        kwargs["cancel_url"] = cancel
        kwargs["user"] = self.request.user
        if self.object:
            kwargs.setdefault("initial", {})
            kwargs["initial"].update({
                "lender_name": self.object.lender.name,
                "lender": self.object.lender_id,
            })
        return kwargs
    

class CreditCardUpdateView(UpdateView):
    model = CreditCard
    form_class = CreditCardForm
    template_name = "liabilities/credit_form.html"
    success_url = reverse_lazy("liabilities:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cancel = self.request.GET.get("next") or reverse("liabilities:list")
        kwargs["cancel_url"] = cancel
        if self.object:
            kwargs.setdefault("initial", {})
            kwargs["initial"].update({
                "issuer_name": self.object.issuer.name,
                "issuer": self.object.issuer_id,
            })
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Credit card updated successfully!")
        return response


class CreditCardDeleteView(DeleteView):
    model = CreditCard
    template_name = "liabilities/credit_confirm_delete.html"
    success_url = reverse_lazy("liabilities:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Credit card deleted.")
        return super().delete(request, *args, **kwargs)


class LoanUpdateView(UpdateView):
    model = Loan
    form_class = LoanForm
    template_name = "liabilities/loan_form.html"
    success_url = reverse_lazy("liabilities:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        cancel = self.request.GET.get("next") or reverse("liabilities:list")
        kwargs["cancel_url"] = cancel
        kwargs["user"] = self.request.user
        if self.object:
            kwargs.setdefault("initial", {})
            kwargs["initial"].update({
                "lender_name": self.object.lender.name,
                "lender": self.object.lender_id,
            })
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Loan updated successfully!")
        return response


class LoanDeleteView(DeleteView):
    model = Loan
    template_name = "liabilities/loan_confirm_delete.html"
    success_url = reverse_lazy("liabilities:list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Loan deleted.")
        return super().delete(request, *args, **kwargs)
       