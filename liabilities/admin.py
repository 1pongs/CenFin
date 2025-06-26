from django.contrib import admin

from .models import Lender, Loan, LoanPayment, CreditCard


class LoanPaymentInline(admin.TabularInline):
    model = LoanPayment
    extra = 0


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    inlines = [LoanPaymentInline]
    list_display = ["lender", "principal_amount", "outstanding_balance"]


admin.site.register(Lender)
admin.site.register(CreditCard)
