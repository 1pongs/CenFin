from django import template
from ..views import CARD_FIELDS_BY_CATEGORY, CARD_SUMMARY_FIELDS_BY_CATEGORY
from insurance.models import Insurance

register = template.Library()

@register.inclusion_tag('acquisitions/_acquisition_card.html', takes_context=True)
def render_acquisition_card(context, acq, urgent=False):
    """Render an acquisition card and include related insurance when needed."""
    field_list = CARD_FIELDS_BY_CATEGORY.get(acq.category, [])
    summary_list = CARD_SUMMARY_FIELDS_BY_CATEGORY.get(acq.category, [])
    insurance = None
    field_tags = []
    if acq.category == 'insurance':
        insurance = acq.insurances.first()
        if insurance:
            if insurance.policy_owner:
                field_tags.append(("Policy Owner", insurance.policy_owner))
            if insurance.person_insured:
                field_tags.append(("Insured", insurance.person_insured))
            if insurance.provider:
                field_tags.append(("Provider", insurance.provider))
    return {
        'acq': acq,
        'field_list': field_list,
        'summary_list': summary_list,
        'field_tags': field_tags,
        'urgent': urgent,
        'insurance': insurance,
        'request': context.get('request'),
    }

@register.filter
def attr(obj, name):
    if name == "date_bought":
        return obj.purchase_tx.date if obj.purchase_tx else ""
    if name == "amount":
        return obj.purchase_tx.amount if obj.purchase_tx else None
    if name == "status":
        if obj.sell_tx:
            return "Sold"
        return obj.get_status_display()
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