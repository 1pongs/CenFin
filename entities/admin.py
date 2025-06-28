from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Entity
# Register your models here.

def soft_delete_selected(modeladmin, request, queryset):
    protected = queryset.filter(is_system_default=True)
    for obj in queryset.exclude(is_system_default=True):
        obj.delete()
    if protected.exists():
        from django.contrib import messages
        messages.error(request, "Cannot delete system entities.")
soft_delete_selected.short_description=_("Soft delete selected %(verbose_name_plural)s")

@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ('entity_name', 'is_active')
    readonly_fields = ('is_system_default',)

    actions=['soft_delete_selected']

    def get_actions(self, request):
        actions=super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def delete_model(self, request, obj):
        if obj.is_system_default:
            from django.contrib import messages
            messages.error(request, "Cannot delete system entities.")
            return
        obj.delete()
