from django.views.generic import TemplateView

from .models import Loan, CreditCard


class LiabilityListView(TemplateView):
    template_name = "liabilities/liability_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tab = self.request.GET.get("tab", "credit")
        ctx["tab"] = tab
        ctx["credit_cards"] = CreditCard.objects.filter(user=self.request.user)
        ctx["loans"] = Loan.objects.filter(user=self.request.user)
        return ctx