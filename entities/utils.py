from .models import Entity


def ensure_fixed_entities():
    """Return the Outside and Account entities, creating them if needed."""
    outside, _ = Entity.objects.get_or_create(
        entity_name="Outside",
        user=None,
        defaults={"entity_type": "outside", "is_visible": False},
    )
    account, _ = Entity.objects.get_or_create(
        entity_name="Account",
        user=None,
        defaults={"entity_type": "free fund", "is_visible": False},
    )
    return outside, account
