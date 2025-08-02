from django.conf import settings


class DisplayCurrencyMiddleware:
    """Attach the chosen display currency code to the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        code = request.session.get("display_currency", settings.BASE_CURRENCY)
        request.display_currency = code
        response = self.get_response(request)
        return response