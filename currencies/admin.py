from django.contrib import admin

from .models import Currency, ExchangeRate


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active"]


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        "currency_from",
        "currency_to",
        "rate",
    ]
    list_filter = ["currency_from", "currency_to"]