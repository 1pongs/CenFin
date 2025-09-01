from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from currencies.models import Currency
from currencies.services import CurrencySourceError


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class NavbarTransactionButtonTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        Currency.objects.create(code="PHP", name="Peso")

    @patch("currencies.context_processors.services.get_frankfurter_currencies", side_effect=CurrencySourceError)
    def test_add_transaction_link_visible(self, mock_currencies):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(resp, reverse("transactions:transaction_create"))