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


class NoStoreCacheMiddleware:
    """Add no-store cache headers so browser Back won't show stale pages.

    Applied globally after authentication; primarily affects authenticated pages
    so that after deleting an object, navigating back forces a re-fetch and the
    view can return a 404 instead of a cached detail page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            # Only disable caching for authenticated sessions to avoid hurting
            # anonymous/static page performance.
            if getattr(request, "user", None) and request.user.is_authenticated:
                # Conservative set of headers to prevent storing in history cache
                response.headers["Cache-Control"] = (
                    "no-store, no-cache, must-revalidate, max-age=0"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
        except Exception:
            # Never fail request processing due to header manipulation
            pass
        return response
