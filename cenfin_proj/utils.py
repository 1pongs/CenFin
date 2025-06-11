from decimal import Decimal
from django.db.models import Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce

from accounts.models import Account
from entities.models import Entity


def get_account_balances():
    """Return active accounts annotated with their current balance."""
    return (
        Account.objects.active()
        .annotate(
            inflow=Coalesce(
                Sum("transaction_as_destination__amount"),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
            outflow=Coalesce(
                Sum("transaction_as_source__amount"),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
        )
        .annotate(balance=F("inflow") - F("outflow"))
        .order_by("account_name")
    )


def get_entity_balances():
    """Return active entities annotated with their current balance."""
    return (
        Entity.objects.active()
        .annotate(
            inflow=Coalesce(
                Sum("transaction_entity_destination__amount"),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
            outflow=Coalesce(
                Sum("transaction_entity_source__amount"),
                Value(Decimal("0.00"), output_field=DecimalField()),
            ),
        )
        .annotate(balance=F("inflow") - F("outflow"))
        .order_by("entity_name")
    )