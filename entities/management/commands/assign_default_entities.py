from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from entities.utils import ensure_fixed_entities


class Command(BaseCommand):
    help = "Ensure the given user owns Outside and Account entities"

    def add_arguments(self, parser):
        parser.add_argument(
            "user_id", type=int, help="ID of the user to own the default entities"
        )

    def handle(self, *args, **options):
        user_id = options["user_id"]
        User = get_user_model()
        user = User.objects.get(pk=user_id)
        outside, account = ensure_fixed_entities(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured entities for {user.username}: {outside.pk}, {account.pk}"
            )
        )
