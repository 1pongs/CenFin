from .models import Account


def ensure_outside_account():
    """Return the shared Outside account, creating it if needed."""
    acc, _ = Account.objects.get_or_create(
        account_name="Outside",
        user=None,
        defaults={"account_type": "Outside", "is_visible": False},
    )
    return acc