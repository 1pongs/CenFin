from django.core.management.base import BaseCommand
from entities.utils import ensure_fixed_entities
from accounts.utils import ensure_outside_account

class Command(BaseCommand):
    help = "Ensure Outside and Account entities and Outside account exist"

    def handle(self, *args, **options):
        outside, account = ensure_fixed_entities()
        acc = ensure_outside_account()
        self.stdout.write(self.style.SUCCESS(
            f"Ensured entities: {outside.entity_name}, {account.entity_name}; account: {acc.account_name}"))