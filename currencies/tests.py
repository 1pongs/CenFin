from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch

from .models import Currency, ExchangeRate


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ActiveCurrenciesEndpointTests(TestCase):
    def setUp(self):
        self.cur1 = Currency.objects.create(code="USD", name="US Dollar")
        Currency.objects.create(code="XXX", name="Old", is_active=False)
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p", email="u@example.com")
        self.client.force_login(self.user)

    def test_active_endpoint_returns_active(self):
        resp = self.client.get(reverse("currencies:active-currencies"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["currencies"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["code"], "USD")


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ExchangeRateCRUDTests(TestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.php = Currency.objects.create(code="PHP", name="Peso")
        User = get_user_model()
        self.owner = User.objects.create_user(username="o", password="p", email="o@example.com")
        self.other = User.objects.create_user(username="x", password="p", email="x@example.com")
        self.rate = ExchangeRate.objects.create(
            source="USER",
            currency_from=self.usd,
            currency_to=self.php,
            rate=1,
            user=self.owner,
        )

    def test_login_required(self):
        resp = self.client.get(reverse("currencies:rate-list"))
        self.assertEqual(resp.status_code, 302)

    def test_owner_only_update_and_delete(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse("currencies:rate-edit", args=[self.rate.pk]))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(reverse("currencies:rate-delete", args=[self.rate.pk]))
        self.assertEqual(resp.status_code, 404)
        self.client.force_login(self.owner)
        resp = self.client.post(reverse("currencies:rate-delete", args=[self.rate.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ExchangeRate.objects.filter(pk=self.rate.pk).exists())


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class CurrencyListBySourceTests(TestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.php = Currency.objects.create(code="PHP", name="Peso")
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p", email="u@example.com")
        self.client.force_login(self.user)

    def test_rc_a_list(self):
        with patch("currencies.views.services.get_rc_a_currencies") as mock:
            mock.return_value = [{"id": self.usd.id, "code": "USD", "name": "US Dollar"}]
            resp = self.client.get(reverse("currencies:currency-list", args=["RC_A"]))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["currencies"], mock.return_value)

    def test_xe_list(self):
        with patch("currencies.views.services.get_xe_currencies") as mock:
            mock.return_value = [{"id": self.php.id, "code": "PHP", "name": "Peso"}]
            resp = self.client.get(reverse("currencies:currency-list", args=["XE"]))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["currencies"], mock.return_value)