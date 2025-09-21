"""Management command to simulate an acquisition delete via Django test Client and print session/log details.

Usage: ./manage.py debug_delete_acq --username <username> --acq <acquisition_id>

This is intended for local debugging only and may be removed later.
"""

from django.core.management.base import BaseCommand
from django.test import Client
from django.contrib.auth import get_user_model
import sys


class Command(BaseCommand):
    help = "Simulate POST to acquisition delete view and print session and responses for debugging"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--acq", required=True, type=int)

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            self.stderr.write("User not found: %s" % options["username"])
            sys.exit(2)

        c = Client()
        # Authenticate the test client. Use force_login which doesn't require
        # knowing the user's password and works reliably in tests.
        try:
            c.force_login(user)
        except Exception:
            # Fall back to normal login attempt if force_login isn't available
            c.login(username=options["username"], password="password")
        delete_url = "/acquisitions/%s/delete/" % options["acq"]
        # Get the deletion confirmation page first (to get csrf cookie/session)
        # Ensure requests use a host allowed by Django's ALLOWED_HOSTS to avoid
        # DisallowedHost during test client requests (use localhost).
        resp_get = c.get(delete_url, HTTP_HOST="localhost")
        self.stdout.write("GET delete status: %s" % resp_get.status_code)
        # Submit the POST
        # Do not follow redirects so we can inspect the session before the
        # acquisitions list view pops the undo keys from session.
        resp_post = c.post(delete_url, follow=False, HTTP_HOST="localhost")
        self.stdout.write(
            "\nPOST delete status (no-follow): %s" % resp_post.status_code
        )
        self.stdout.write("Response headers: %s" % dict(resp_post.items()))
        if resp_post.status_code in (301, 302):
            self.stdout.write("Redirect location: %s" % resp_post.get("Location"))
        # Print cookies and session keys
        self.stdout.write("\nCookies:")
        for k, v in c.cookies.items():
            self.stdout.write("  %s=%s" % (k, v.value))
        try:
            session = c.session
            self.stdout.write("\nSession keys:")
            for k in session.keys():
                self.stdout.write("  %s = %s" % (k, session[k]))
        except Exception as e:
            self.stdout.write("Could not read client session: %s" % e)

        # Print any messages in response content if present (simple search)
        content = resp_post.content.decode("utf-8", errors="replace")
        if "Acquisition deleted" in content:
            self.stdout.write('\nFound "Acquisition deleted" in response content')
        else:
            self.stdout.write(
                "\nDid not find deletion confirmation in response content"
            )
