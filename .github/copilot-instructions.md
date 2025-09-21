<!-- Copilot instructions for the CenFin repository -->
# CenFin — AI coding agent guidance

Purpose: be immediately productive when editing this Django-based personal-finance app.

- Project type: Django 5.2 monolith with several apps: `dashboard`, `transactions`, `accounts`, `entities`, `currencies`, `acquisitions`, `liabilities`, `users`.
- Dev tooling: Python requirements in `requirements.txt`; Node devtools for frontend tests in `package.json` (see `npm run test` for `jest`, `npm run e2e` for Playwright).

Key architectural notes
- BASE_CURRENCY: global default in `cenfin_proj/settings.py` (e.g. `BASE_CURRENCY = "PHP"`). Many views/mixins read `request.display_currency` or `settings.BASE_CURRENCY`.
- Display currency flow: `core.middleware.DisplayCurrencyMiddleware` sets `request.display_currency`; `currencies.context_processors.currency_context` provides `currency_options` for templates. Use `currencies.services.get_frankfurter_currencies()` to fetch remote currency lists (cached).
- Auth and access: custom user model `users.User` (`AUTH_USER_MODEL` in settings) and `users.access.LoginRequiredMiddleware` which redirects anonymous users to login for most paths. Tests set `TESTING` flag via settings detection.
- External services: currency rates come from Frankfurter (`currencies.services`). The service uses Django cache and raises `CurrencySourceError` on transient failures — consumers catch this and fall back to local DB.
- Transactions: `transactions` app contains complex domain logic (reversals, hidden rows, parent_transfer relations). Use `Transaction.all_objects` to access hidden or deleted/reversed rows; normal managers hide reversal rows.

Patterns & conventions (concrete examples)
- Services layer: small modules under app `services.py` (example: `currencies/services.py`) which encapsulate external calls, caching, and domain-specific exceptions (`CurrencySourceError`). Prefer to call or mock these services in views/tests instead of duplicating HTTP logic.
- Context processors: `currencies/context_processors.py` is used to ensure DB `Currency` objects exist for remote codes; it updates `Currency` names when Frankfurter returns new labels.
- Middleware: `core.middleware.DisplayCurrencyMiddleware` attaches `display_currency` to the request; prefer that over reading sessions directly in views.
- Managers and non-default querysets: some models expose `all_objects` to include hidden/reversal rows. Example: `transactions/models.py` uses `Transaction.all_objects` in undo/delete flows and management commands.
- Feature flags in tests: `cenfin_proj/settings.py` sets `TESTING = any(arg in ('pytest', 'test') for arg in sys.argv)`. Some middleware short-circuits when `TESTING` is True — tests rely on this.

Developer workflows (commands and test guidance)
- Run Django management tasks through `manage.py`: `python manage.py runserver`, `python manage.py migrate`, `python manage.py test` (or `pytest` if installed).
- Tests: Python unit tests live per-app (e.g. `transactions/tests.py`, many files under `tests/` folder). The project uses an in-memory sqlite DB when `TESTING` is True; continuous integration should run `python -m pytest` or `python manage.py test`.
- Frontend tests: Node scripts in `package.json`: `npm test` runs `jest`; `npm run e2e` runs Playwright. Use `playwright.config.js` to configure browsers.

Editing guidance for AI agents
- When touching currency code paths, update both: `currencies/services.py` (external fetch/caching) and `currencies/context_processors.py` (DB sync + template context).
- For changes to transaction logic, search for uses of `Transaction.all_objects` and `is_reversal`/`is_reversed` flags; the undo/reversal flow is intentionally explicit (see `transactions/views.py` for `_reverse_and_hide` and `transaction_undo_delete`).
- Preserve tests' expectations about `TESTING` behavior. Avoid altering `cenfin_proj/settings.py` test-detection unless you update tests accordingly.
- Prefer small, focused changes with accompanying unit tests. Look at `tests/` for existing patterns (patching services, using `@patch("currencies.context_processors.services.get_frankfurter_currencies"...)` in tests).

Examples (copy/paste friendly)
- Use the service and handle its domain error:
  try:
      data = currencies.services.get_frankfurter_currencies()
  except currencies.services.CurrencySourceError:
      # fall back to local DB or cached data
      ...

- Access display currency on request rather than session directly:
  code = getattr(request, "display_currency", settings.BASE_CURRENCY)

Files to read first (most relevant)
- `cenfin_proj/settings.py` — global defaults and TESTING behavior
- `core/middleware.py` — DisplayCurrencyMiddleware
- `currencies/services.py` and `currencies/context_processors.py` — external currency fetch + template supply
- `users/access.py` — login middleware patterns
- `transactions/views.py` and `transactions/models.py` — domain logic for reversals and hidden rows

If you need more context
- Search for `all_objects`, `is_reversal`, `display_currency`, `BASE_CURRENCY`, and `CurrencySourceError` to find related places.

Please review any unclear sections or missing conventions you'd like expanded and I'll iterate.
