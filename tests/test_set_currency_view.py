from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from currencies.models import Currency


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class SetCurrencyViewTests(TestCase):
    def setUp(self):
        self.cur = Currency.objects.create(code="USD", name="US Dollar")
        User = get_user_model()
        self.user = User.objects.create_user(username="u", password="p")

    def test_logged_in_post_sets_session_and_redirects(self):
        self.client.force_login(self.user)
        url = reverse("set_currency")
        resp = self.client.post(url + "?next=/home/", {"code": self.cur.code})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/home/")
        self.assertEqual(self.client.session["active_currency"], self.cur.code)

    def test_post_next_field_used_when_present(self):
        self.client.force_login(self.user)
        url = reverse("set_currency")
        resp = self.client.post(url, {"code": self.cur.code, "next": "/here/"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/here/")
        self.assertEqual(self.client.session["active_currency"], self.cur.code)

    def test_anonymous_redirects_to_login(self):
        url = reverse("set_currency")
        resp = self.client.post(url, {"code": self.cur.code})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse(settings.LOGIN_URL), resp["Location"])