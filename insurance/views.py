from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy

from .models import Insurance
from .forms import InsuranceForm


class InsuranceListView(ListView):
    model = Insurance
    template_name = "insurance/insurance_list.html"

    def get_queryset(self):
        return Insurance.objects.filter(user=self.request.user).with_cash_value().with_total_premiums_paid()


class InsuranceCreateView(CreateView):
    model = Insurance
    form_class = InsuranceForm
    template_name = "insurance/insurance_form.html"
    success_url = reverse_lazy("insurance:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class InsuranceDetailView(DetailView):
    model = Insurance
    template_name = "insurance/insurance_detail.html"

    def get_queryset(self):
        return (
            Insurance.objects.filter(user=self.request.user)
            .with_cash_value()
            .with_total_premiums_paid()
        )