from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from entities.models import Entity

class Command(BaseCommand):
    help = "Assign Outside and Account entities (ids 1 and 2) to the given user."

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int, help='ID of the user to own the default entities')

    def handle(self, *args, **options):
        user_id = options['user_id']
        User = get_user_model()
        user = User.objects.get(pk=user_id)
        updated = Entity.objects.filter(id__in=[1, 2]).update(user=user)
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} entities for user {user.username}"))
