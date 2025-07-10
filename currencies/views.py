"""Views for managing exchange rates."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from .models import ExchangeRate
from .forms import ExchangeRateForm


class ExchangeRateListView(ListView):
    model = ExchangeRate
    template_name = "currencies/rate_list.html"

    def get_queryset(self):
        qs = super().get_queryset().filter(user=self.request.user)
        return qs.order_by("currency_from__code", "currency_to__code")


class ExchangeRateCreateView(CreateView):
    model = ExchangeRate
    form_class = ExchangeRateForm
    template_name = "currencies/rate_form.html"
    success_url = reverse_lazy("currencies:rate-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class ExchangeRateUpdateView(UpdateView):
    model = ExchangeRate
    form_class = ExchangeRateForm
    template_name = "currencies/rate_form.html"
    success_url = reverse_lazy("currencies:rate-list")

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)