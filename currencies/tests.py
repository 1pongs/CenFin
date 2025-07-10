from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch
from django.core.cache import cache

from .models import Currency, ExchangeRate
from . import services


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

    def test_rem_a_list(self):
        with patch("currencies.views.services.get_rem_a_currencies") as mock:
            mock.return_value = {"USD": "US Dollar"}
            resp = self.client.get(reverse("currencies:currency-list") + "?source=REM_A")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), mock.return_value)

    def test_frankfurter_list(self):
        with patch("currencies.views.services.get_frankfurter_currencies") as mock:
            mock.return_value = {"PHP": "Peso"}
            resp = self.client.get(reverse("currencies:currency-list") + "?source=FRANKFURTER")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), mock.return_value)
            
            
class FrankfurterServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_fetch_and_cache(self):
        sample = {"EUR": "Euro"}
        Currency.objects.create(code="EUR", name="Euro")
        with patch("currencies.services.requests.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.status_code = 200
            mock_resp.json.return_value = sample
            data1 = services.get_frankfurter_currencies()
            data2 = services.get_frankfurter_currencies()
            self.assertEqual(data1, sample)
            self.assertEqual(data2, sample)
            mock_get.assert_called_once()

    def test_error_uses_cache_then_raises(self):
        Currency.objects.create(code="EUR", name="Euro")
        cache.set(services.FRANKFURTER_CACHE_KEY, {"EUR": "Euro"}, 86400)
        with patch("currencies.services.requests.get", side_effect=Exception("x")):
            data = services.get_frankfurter_currencies()
            self.assertEqual(data, {"EUR": "Euro"})
        cache.clear()
        with patch("currencies.services.requests.get", side_effect=Exception("x")):
            with self.assertRaises(services.CurrencySourceError):
                services.get_frankfurter_currencies()


class ApiCurrenciesViewTests(TestCase):
    def setUp(self):
        self.cur = Currency.objects.create(code="USD", name="US Dollar")
        User = get_user_model()
        self.user = User.objects.create_user(username="v", password="p")
        self.client.force_login(self.user)

    def test_frankfurter_success(self):
        sample = {"USD": "US Dollar"}
        with patch("currencies.services.requests.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.status_code = 200
            mock_resp.json.return_value = sample
            resp = self.client.get(reverse("api_currencies") + "?source=FRANKFURTER")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), sample)

    def test_frankfurter_failure(self):
        with patch("currencies.services.requests.get", side_effect=Exception("x")):
            resp = self.client.get(reverse("api_currencies") + "?source=FRANKFURTER")
            self.assertEqual(resp.status_code, 502)
            self.assertEqual(resp.json(), {})