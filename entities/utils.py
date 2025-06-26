from .models import Entity


def ensure_fixed_entities(user=None):
    """Return the Outside and Account entities, creating them if needed."""
    outside, _ = Entity.objects.get_or_create(
        entity_name="Outside",
        user=user,
        defaults={"entity_type": "outside", "is_visible": False},
    )
    account, created = Entity.objects.get_or_create(
        entity_name="Account",
        user=user,
        defaults={"entity_type": "free fund", "is_visible": True},
    )
    if not created and not account.is_visible:
        account.is_visible = True
        account.save(update_fields=["is_visible"])
    return outside, account
