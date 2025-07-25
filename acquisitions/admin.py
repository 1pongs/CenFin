from django.contrib import admin
from .models import Acquisition

# Register your models here.

@admin.register(Acquisition)
class AcquisitionAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "purchase_tx", "sell_tx")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        cat = obj.category if obj else request.POST.get('category')
        if cat != 'stock_bond':
            form.base_fields.pop('current_value', None)
            form.base_fields.pop('market', None)
        if cat != 'property':
            form.base_fields.pop('expected_lifespan_years', None)
            form.base_fields.pop('location', None)
        if cat != 'insurance':
            form.base_fields.pop('insurance_type', None)
            form.base_fields.pop('sum_assured_amount', None)
            form.base_fields.pop('cash_value', None)
            form.base_fields.pop('maturity_date', None)
            form.base_fields.pop('provider', None)
        return form
