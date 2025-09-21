# One-off script to call AcquisitionDeleteView with RequestFactory and inspect session
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth import get_user_model
from acquisitions.views import AcquisitionDeleteView

User = get_user_model()
user = User.objects.get(username="encinasjr")
rf = RequestFactory()
req = rf.post("/acquisitions/4/delete/")
req.user = user
# SessionMiddleware expects a get_response callable; provide a noop.
sm = SessionMiddleware(lambda r: None)
sm.process_request(req)
req.session.save()
view = AcquisitionDeleteView.as_view()
resp = view(req, pk=4)
print("resp:", resp)
try:
    print("session after in-script:", dict(req.session.items()))
except Exception as e:
    print("failed reading session after:", e)
