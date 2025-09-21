from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from accounts.models import Account

# Register your models here.


def soft_delete_selected(modeladmin, request, queryset):
    for obj in queryset:
        obj.delete()


soft_delete_selected.short_description = _(
    "Soft delete selected %(verbose_name_plural)s"
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("account_name", "currency", "is_active")

    actions = ["soft_delete_selected"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def delete_model(self, request, obj):
        obj.delete()
