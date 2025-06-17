from django import template
from ..views import CARD_FIELDS_BY_CATEGORY, CARD_SUMMARY_FIELDS_BY_CATEGORY

register = template.Library()

@register.inclusion_tag('acquisitions/_acquisition_card.html')
def render_acquisition_card(acq, urgent=False):
    field_list = CARD_FIELDS_BY_CATEGORY.get(acq.category, [])
    summary_list = CARD_SUMMARY_FIELDS_BY_CATEGORY.get(acq.category, [])
    return {
        'acq': acq,
        'field_list': field_list,
        'summary_list': summary_list,
        'urgent': urgent,
    }

@register.filter
def attr(obj, name):
    if name == "date_bought":
        return obj.purchase_tx.date
    if name == "amount":
        return obj.purchase_tx.amount
    if name == "status":
        return "Sold" if obj.sell_tx else "Owned"
    return getattr(obj, name)


@register.filter
def replace(value, args):
    """Replace ``old`` with ``new`` in ``value``.

    Usage::
        {{ value|replace:"old,new" }}

    ``old`` and ``new`` are separated by a comma to comply with
    Django's single-argument filter syntax.
    """
    try:
        old, new = args.split(",", 1)
    except ValueError:
        return value
    return str(value).replace(old, new)


@register.filter
def city(value):
    """Return just the city/municipality portion of a location string."""
    if not value:
        return ""
    loc = value.split(',')[0].strip()
    parts = loc.split()
    if len(parts) >= 2 and parts[1].lower() in ("city", "municipality"):
        return " ".join(parts[:2])
    return parts[0]