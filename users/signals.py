from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.utils import ensure_outside_account
from entities.utils import ensure_fixed_entities


@receiver(post_save, sender=get_user_model())
def ensure_defaults_exist(sender, instance, created, **kwargs):
    """Create default entities for the new user and ensure shared records exist."""
    if created:
        # per-user default entities
        ensure_fixed_entities(instance)
        # shared outside account remains global
        ensure_outside_account()
