from django.core.management.base import BaseCommand
from entities.models import Entity

class Command(BaseCommand):
    help = "Delete Entity rows with no associated user"

    def handle(self, *args, **options):
        qs = Entity.objects.filter(user__isnull=True)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} orphan entities"))