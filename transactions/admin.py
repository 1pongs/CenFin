from django.contrib import admin
from .models import Transaction

# Register your models here.


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "description",
        "account_source",
        "account_destination",
        "entity_source",
        "entity_destination",
        "amount",
        "remarks",
    )
    list_filter = ("date", "description")
    search_fields = ("description",)
