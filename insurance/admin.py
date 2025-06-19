from django.contrib import admin
from .models import Insurance, PremiumPayment


@admin.register(Insurance)
class InsuranceAdmin(admin.ModelAdmin):
    list_display = ("name", "insurance_type", "sum_assured")


@admin.register(PremiumPayment)
class PremiumPaymentAdmin(admin.ModelAdmin):
    list_display = ("insurance", "date", "amount")

