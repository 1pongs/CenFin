from .models import Entity


def ensure_fixed_entities(user=None):
    """Return the Outside and Account entities for ``user``.

    When ``user`` is ``None`` the function will **not** create any new rows and
    simply return existing records if they exist. This behaviour keeps older
    migrations that called this utility without a user from creating orphaned
    entities with ``user_id`` set to ``NULL``.
    """

    if user is None:
        outside = Entity.objects.filter(entity_name="Outside", user__isnull=True).first()
        account = Entity.objects.filter(entity_name="Account", user__isnull=True).first()
        return outside, account
    
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
