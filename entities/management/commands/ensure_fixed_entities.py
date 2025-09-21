from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from entities.utils import ensure_fixed_entities
from accounts.utils import ensure_outside_account


class Command(BaseCommand):
    help = "Ensure Outside and Account entities and Outside account exist for a user"

    def add_arguments(self, parser):
        parser.add_argument("user_id", type=int, help="User ID")

    def handle(self, *args, **options):
        user_id = options["user_id"]
        User = get_user_model()
        user = User.objects.get(pk=user_id)
        outside, account = ensure_fixed_entities(user)
        acc = ensure_outside_account()
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured entities for {user.username}; account: {acc.account_name}"
            )
        )
