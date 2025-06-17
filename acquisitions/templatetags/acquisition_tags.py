from django import template
from ..views import CARD_FIELDS_BY_CATEGORY

register = template.Library()

@register.inclusion_tag('acquisitions/_acquisition_card.html')
def render_acquisition_card(acq, field_list, urgent=False):
    return {'acq': acq, 'field_list': field_list, 'urgent': urgent}


@register.filter
def attr(obj, name):
    if name == "date_bought":
        return obj.purchase_tx.date
    if name == "amount":
        return obj.purchase_tx.amount
    if name == "status":
        return "Sold" if obj.sell_tx else "Owned"
    return getattr(obj, name)