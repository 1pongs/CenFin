from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login

class LoginRequiredMiddleware:
    """Redirect anonymous users to the login page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)

        if not request.user.is_authenticated:
            path = request.path_info
            if not path.startswith('/users/') and not path.startswith('/admin/') and not path.startswith(settings.STATIC_URL):
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        return self.get_response(request)


class AccessRequiredMixin(LoginRequiredMixin):
    """Alias for Django's LoginRequiredMixin."""
    pass

require_login = login_required