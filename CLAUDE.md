# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev server (defaults to http://localhost:8000)
python manage.py runserver

# Run the full test suite (28 tests)
python manage.py test tests

# Run a single test file / class / method
python manage.py test tests.test_chat
python manage.py test tests.test_chat.MessageTests
python manage.py test tests.test_chat.MessageTests.test_send_message_auto_titles_session

# Migrations
python manage.py makemigrations
python manage.py migrate

# Shell with project context
python manage.py shell
```

Tests live under `tests/` (project-level), not inside each app. They use `APITestCase` with `reverse()` for URL lookups and **must mock Claude** — `apps.<app>.views.<claude_function>` — so the suite stays offline and deterministic. Look at `tests/test_chat.py` and `tests/test_analyzer.py` for the pattern.

## Architecture

### App layout

Three feature apps live under `apps/` (not at the project root). They're imported as `apps.users`, `apps.chat`, `apps.analyzer` and registered as such in `INSTALLED_APPS`. A new app must be created with `python manage.py startapp <name> apps/<name>` and added with the `apps.` prefix.

- **`apps.users`** — Custom email-only user model (`AUTH_USER_MODEL = "users.User"`, no `username` field) + JWT auth views (register/login/refresh/logout/me).
- **`apps.chat`** — `ChatSession` 1:N `Message`. On `POST /messages/`, the view persists the user message, replays the full session history to Claude, persists the assistant reply, and auto-titles the session from the first user message.
- **`apps.analyzer`** — Stateless OWASP Top 10 scanner. The `claude.py` system prompt forces JSON-only output; the view strips accidental markdown fences and returns either the parsed-and-revalidated payload or the raw dict if the structure is unexpected.

`config/` holds settings, the root URL router, `middleware.py` (`RequestAuditMiddleware` logs `METHOD PATH STATUS DURATIONms` to the `audit` logger), and WSGI/ASGI entrypoints.

### Claude integration

Each Claude-backed app has its own `claude.py` with its system prompt and a thin client function. The model id is centralised at `settings.CLAUDE_MODEL`. Views catch `anthropic.APIError` and surface it as `502 Bad Gateway`; the analyzer also catches `json.JSONDecodeError` / `KeyError` / `ValueError` as `502`. New Claude-backed endpoints should follow this pattern: keep prompts and API calls in a module-level `claude.py`, keep views thin, and surface errors as `502`.

### Throttling

DRF throttling is configured with **named scopes** in `config/settings.py` (`user`, `claude_chat`, `claude_scan`). Custom scopes are wired through `apps/throttles.py` (a `UserRateThrottle` subclass per scope) and applied per-view either via `throttle_classes` or `get_throttles()` (used in `apps.chat.views.MessageListCreateView` to apply `claude_chat` only on `POST`, not `GET`). Any new Claude-backed view should get its own scope, not reuse `user`.

### Auth model

Simple JWT is configured with **rotation + blacklist after rotation** — every successful refresh invalidates the old refresh token. Logout blacklists the supplied refresh token explicitly. The default DRF permission is `IsAuthenticated`; public endpoints must override with `permission_classes = [AllowAny]`.

### OpenAPI / Swagger

`drf-spectacular` generates the schema from view signatures and serializers. Use `@extend_schema(...)` on every new view so it appears correctly in Swagger UI at `/api/docs/`. Swagger and the raw schema (`/api/schema/`) are unauthenticated; the root path `/` 302-redirects to `/api/docs/`.

## Config & deploy gotchas

- **`SECRET_KEY`** uses `os.environ[...]` (not `getenv`) but is wrapped in a `try/except KeyError` that raises `ImproperlyConfigured` with a generation command. Don't unwrap it.
- **`ANTHROPIC_API_KEY`** is enforced at startup (`ImproperlyConfigured`) only when `DEBUG=False`. In dev, chat and analyzer endpoints will fail at request time if it's missing.
- **`DATABASE_URL`** is optional in dev — `dj-database-url` falls back to `sqlite:///db.sqlite3`. PostgreSQL is required in production.
- **SSL is delegated to the Railway proxy.** `SECURE_SSL_REDIRECT = False` and `SECURE_HSTS_SECONDS = 0` are intentional — Django trusts `X-Forwarded-Proto` via `SECURE_PROXY_SSL_HEADER`. Re-enabling `SECURE_SSL_REDIRECT` behind a TLS-terminating proxy causes redirect loops.
- **Deploy is Railway-driven**: `Procfile` declares `release: python manage.py migrate` and `web: gunicorn config.wsgi:application`. The `.env` file is git-ignored; production env vars must be set in the Railway dashboard.
- **Static files** are served by WhiteNoise with `CompressedManifestStaticFilesStorage`. `collectstatic` runs automatically on Railway during the build.

## Conventions

- Views are thin `APIView` subclasses; business logic (especially Claude calls) lives in helper modules (`claude.py`).
- Object ownership is enforced by filtering `Model.objects.filter(..., user=request.user)` and returning `404` for cross-user access (see `_get_session` in `apps.chat.views`). Never expose a `PermissionDenied` that leaks existence.
- Comments are reserved for non-obvious "why" — well-named code is the default documentation.
- The `migrations/` directories are committed and authoritative; run `makemigrations` for any model change.
