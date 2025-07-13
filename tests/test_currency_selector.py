from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from currencies.models import Currency


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class CurrencySelectorTests(TestCase):
    def setUp(self):
        self.cur_usd = Currency.objects.create(code="USD", name="US Dollar")
        self.cur_php = Currency.objects.create(code="PHP", name="Peso")
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p", email="u@example.com", base_currency=self.cur_usd)
        self.client.force_login(self.user)

    def test_navbar_shows_active_currency(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(resp.context["active_currency"].code, self.cur_usd.code)

    def test_navbar_form_has_next_field(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(resp, 'name="next"')
        self.assertContains(resp, 'value="/"')

    def test_set_currency_updates_session(self):
        self.client.post(reverse("set_currency"), {"code": self.cur_php.code})
        self.assertEqual(self.client.session["active_currency"], self.cur_php.code)
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(resp.context["active_currency"].code, self.cur_php.code)

    def test_settings_save_updates_session(self):
        resp = self.client.post(reverse("users:settings"), {
            "first_name": "",
            "last_name": "",
            "email": "u@example.com",
            "base_currency": self.cur_php.id,
            "preferred_rate_source": self.user.preferred_rate_source,
        })
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.base_currency_id, self.cur_php.id)
        self.assertEqual(self.client.session["active_currency"], self.cur_php.code)