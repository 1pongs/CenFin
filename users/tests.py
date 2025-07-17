from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from entities.models import Entity


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class DefaultEntitiesCreatedTest(TestCase):
    def test_new_user_gets_default_entities(self):
        User = get_user_model()
        user = User.objects.create_user(username="def", password="p")

        names = set(user.entities.values_list("entity_name", flat=True))
        self.assertEqual(names, {"Outside", "Account", "Remittance"})

        null_count = Entity.objects.filter(user__isnull=True).count()
        self.assertEqual(null_count, 0)
