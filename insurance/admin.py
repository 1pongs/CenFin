from django.contrib import admin
from .models import Insurance, PremiumPayment


@admin.register(Insurance)
class InsuranceAdmin(admin.ModelAdmin):
    list_display = ("insurance_type", "policy_owner", "sum_assured")


@admin.register(PremiumPayment)
class PremiumPaymentAdmin(admin.ModelAdmin):
    list_display = ("insurance", "date", "amount")

