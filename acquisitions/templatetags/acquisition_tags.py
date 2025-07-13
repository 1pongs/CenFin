from django import template
from ..views import CARD_FIELDS_BY_CATEGORY, CARD_SUMMARY_FIELDS_BY_CATEGORY
from insurance.models import Insurance
from django.template.defaultfilters import floatformat
from django.contrib.humanize.templatetags.humanize import intcomma
from utils.currency import amount_for_display, get_currency_symbol, get_active_currency

register = template.Library()

@register.inclusion_tag('acquisitions/_acquisition_card.html', takes_context=True)
def render_acquisition_card(context, acq):
    """Render an acquisition card and include related insurance when needed."""
    insurance = None
    extra_rows = []
    if acq.category == 'insurance':
        insurance = acq.insurances.first()
        if insurance:
            if insurance.policy_owner:
                extra_rows.append(("Policy Owner", insurance.policy_owner))
            if insurance.person_insured:
                extra_rows.append(("Insured", insurance.person_insured))
            if insurance.provider:
                extra_rows.append(("Provider", insurance.provider))

    request = context.get('request')

    def _fmt_amt(val):
        if val is None:
            return None
        base_code = request.user.base_currency.code if getattr(request.user, 'base_currency_id', None) else 'PHP'
        amt = amount_for_display(request, val, base_code) if request else val
        active = get_active_currency(request) if request else None
        symbol = get_currency_symbol(active.code) if active else ''
        return f"{symbol}{intcomma(floatformat(amt, 2))}"

    rows = [
        ("Type", acq.get_category_display()),
        ("Date Bought", acq.purchase_tx.date if acq.purchase_tx else None),
        ("Amount", _fmt_amt(acq.purchase_tx.amount if acq.purchase_tx else None)),
        ("Status", "Sold" if acq.sell_tx else acq.get_status_display()),
    ] + extra_rows
    return {
        'acq': acq,
        'rows': rows,
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