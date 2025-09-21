from django.apps import AppConfig


class AcquisitionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "acquisitions"

    def ready(self):
        # Import signal handlers
        try:
            from . import signals  # noqa: F401
        except Exception:
            # Avoid crashing app startup if signals have import issues.
            # Views still contain reversal logic; this is an extra safety net.
            pass
