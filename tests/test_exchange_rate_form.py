from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch

from currencies.models import Currency, ExchangeRate


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ExchangeRateFormTests(TestCase):
    def setUp(self):
        Currency.objects.create(code="PHP", name="Philippine Peso")
        Currency.objects.create(code="KRW", name="South Korean Won")
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)

    @patch("currencies.services.get_frankfurter_currencies")
    def test_create_rate_with_valid_codes(self, mock_frank):
        mock_frank.return_value = {
            "KRW": "South Korean Won",
            "PHP": "Philippine Peso",
        }
        resp = self.client.post(
            reverse("currencies:rate-create"),
            {
                "source": "FRANKFURTER",
                "currency_from": "KRW",
                "currency_to": "PHP",
                "rate": "0.04096",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ExchangeRate.objects.count(), 1)
        rate = ExchangeRate.objects.first()
        self.assertIsInstance(rate.currency_from, Currency)
        self.assertEqual(rate.currency_from.code, "KRW")

    @patch("currencies.services.get_frankfurter_currencies")
    def test_invalid_code_shows_error(self, mock_frank):
        mock_frank.return_value = {
            "KRW": "South Korean Won",
            "PHP": "Philippine Peso",
        }
        resp = self.client.post(
            reverse("currencies:rate-create"),
            {
                "source": "FRANKFURTER",
                "currency_from": "XXX",
                "currency_to": "PHP",
                "rate": "0.04096",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.context["form"].errors["currency_from"],
            ["Select a valid currency code."],
        )