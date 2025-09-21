from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Transaction


@receiver(post_delete, sender=Transaction)
def remove_loan_when_disbursement_deleted(sender, instance, **kwargs):
    """Ensure loans vanish if their disbursement transaction is deleted."""
    if instance.transaction_type == "loan_disbursement":
        loan = getattr(instance, "loan_disbursement", None)
        if loan:
            loan.delete()
