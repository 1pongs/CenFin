from django.contrib import admin
from .models import Asset

# Register your models here.

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("name", "purchase_tx", "sell_tx")
