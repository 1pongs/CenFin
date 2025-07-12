from decimal import Decimal
from django import template
from utils.currency import amount_for_display

register = template.Library()

@register.simple_tag(takes_context=True)
def display(context, amount: Decimal, orig_currency):
    request = context.get('request')
    if request is None:
        return amount
    return amount_for_display(request, amount, orig_currency)