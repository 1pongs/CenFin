from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Button
from django.urls import reverse_lazy
from crispy_forms.bootstrap import FormActions
from .models import Entity

class EntityForm(forms.ModelForm):
    class Meta:
        model = Entity
        fields = ["entity_name", "entity_type"]

    def __init__(self, *args, **kwargs):
        show_actions = kwargs.pop("show_actions", True)
        cancel_url = kwargs.pop("cancel_url", reverse_lazy("entities:list"))
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        
        layout_fields = [
            Row(
                Column("entity_name", css_class="col-md-6"),
                Column("entity_type", css_class="col-md-6"),
                css_class="g-3",
            ),
        ]

        if show_actions:
            layout_fields.append(
                FormActions(
                    Submit("save", "Save", css_class="btn btn-primary"),
                    Button(
                        "cancel",
                        "Cancel",
                        css_class="btn btn-outline-secondary",
                        onclick=f"window.location.href='{cancel_url}'",
                        type="button",
                    ),
                    css_class="d-flex justify-content-end gap-2 mt-3",
                )
            )

        self.helper.layout = Layout(*layout_fields)    
