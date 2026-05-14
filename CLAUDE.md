# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev server (defaults to http://localhost:8000)
python manage.py runserver

# Run the full test suite (56 tests)
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

Four apps live under `apps/` (not at the project root). They're imported as `apps.users`, `apps.chat`, `apps.analyzer`, `apps.ratelimit` and registered as such in `INSTALLED_APPS`. A new app must be created with `python manage.py startapp <name> apps/<name>` and added with the `apps.` prefix.

- **`apps.users`** — Custom email-only user model (`AUTH_USER_MODEL = "users.User"`, no `username` field) + JWT auth views (register/login/refresh/logout/me). Register returns a generic `202` and is silent on duplicate email to avoid account enumeration.
- **`apps.chat`** — `ChatSession` 1:N `Message`. On `POST /messages/`, the view persists both messages atomically — the user message and the assistant reply — then returns a `201` body containing `user_message` and `assistant_message`, each a serialized `Message` object. The session is auto-titled from the first user message (up to 80 characters).
- **`apps.analyzer`** — Stateless OWASP Top 10 scanner. The `claude.py` system prompt forces JSON-only output; the view strips accidental markdown fences, re-validates through `ScanResultSerializer`, and surfaces any non-conforming output as `502`.
- **`apps.ratelimit`** — DB-backed daily per-user request limiting. The `RateLimit` model holds one counter row per `(user, endpoint)`; the `@check_rate_limit` decorator (in `decorators.py`) locks the row with `select_for_update`, resets it past `reset_at` (UTC midnight), and returns `429` with a `reset_at` payload once the limit is hit. Independent of DRF throttling.

`config/` holds settings, the root URL router, `middleware.py` (`RequestAuditMiddleware` logs `METHOD PATH STATUS DURATIONms` to the `audit` logger), and WSGI/ASGI entrypoints.

### Claude integration

Each Claude-backed app has its own `claude.py` with its system prompt and a thin client function. The model id is centralised at `settings.CLAUDE_MODEL`. Views catch `anthropic.APIError` and surface it as `502 Bad Gateway`; the analyzer also catches `json.JSONDecodeError` / `KeyError` / `ValueError` as `502`. New Claude-backed endpoints should follow this pattern: keep prompts and API calls in a module-level `claude.py`, keep views thin, and surface errors as `502`.

### Throttling

There are **two independent layers**:

1. **DRF throttling** (cache-backed, per-scope) configured with **named scopes** in `config/settings.py` (`user`, `anon`, `auth`, `claude_chat`, `claude_scan`). Custom scopes are wired through `apps/throttles.py` (`ClaudeChatThrottle`, `ClaudeScanThrottle`, `AuthAnonThrottle`, each re-reading its rate live so `@override_settings` works in tests) and applied per-view via `throttle_classes` or `get_throttles()` (used in `apps.chat.views.MessageListCreateView` to apply `claude_chat` only on `POST`, not `GET`). Any new Claude-backed view should get its own scope, not reuse `user`.
2. **Daily per-user limiting** (DB-backed, in `apps.ratelimit`) applied with the `@check_rate_limit(endpoint=..., limit_key=...)` decorator on the view method; limits live in `settings.RATE_LIMITS` and are env-configurable (`CHAT_DAILY_LIMIT`, `ANALYZER_DAILY_LIMIT`).

The DRF throttle cache backend matters in production: with multiple Gunicorn workers the counters must be shared, so it is Redis (`REDIS_URL`) or the DB cache table `django_cache`, never per-process `LocMemCache`.

### Auth model

Simple JWT is configured with **rotation + blacklist after rotation** — every successful refresh invalidates the old refresh token. Logout blacklists the supplied refresh token explicitly. The default DRF permission is `IsAuthenticated`; public endpoints must override with `permission_classes = [AllowAny]`.

### OpenAPI / Swagger

`drf-spectacular` generates the schema from view signatures and serializers. Use `@extend_schema(...)` on every new view so it appears correctly in Swagger UI at `/api/docs/`. Swagger and the raw schema (`/api/schema/`) are unauthenticated; the root path `/` 302-redirects to `/api/docs/`.

## Config & deploy gotchas

- **`SECRET_KEY`** uses `os.environ[...]` (not `getenv`) but is wrapped in a `try/except KeyError` that raises `ImproperlyConfigured` with a generation command. Don't unwrap it.
- **`ANTHROPIC_API_KEY`** is enforced at startup (`ImproperlyConfigured`) only when `DEBUG=False`. In dev, chat and analyzer endpoints will fail at request time if it's missing.
- **`DATABASE_URL`** is optional in dev — `dj-database-url` falls back to `sqlite:///db.sqlite3`. PostgreSQL is required in production.
- **Only `.env` is loaded.** Both `manage.py` and `config/settings.py` call `environ.Env.read_env(BASE_DIR / ".env")`. There is no `.env.local` support; `.env.example` is the committed template. The `.env` file is git-ignored; production env vars must be set in the Railway dashboard.
- **SSL is delegated to the Railway proxy.** `SECURE_SSL_REDIRECT = False` is intentional — Django trusts `X-Forwarded-Proto` via `SECURE_PROXY_SSL_HEADER`. Re-enabling `SECURE_SSL_REDIRECT` behind a TLS-terminating proxy causes redirect loops. `SECURE_HSTS_SECONDS` is `0` in dev/test and defaults to 1 year when `DEBUG=False`.
- **Deploy is Railway-driven**: `Procfile` declares `release: python manage.py migrate && python manage.py createcachetable` and `web: gunicorn config.wsgi:application --workers 2`. `.python-version` pins the Python runtime for the Nixpacks build.
- **Static files** are served by WhiteNoise with `CompressedManifestStaticFilesStorage`, configured through the **`STORAGES`** setting (Django 5.1 removed the old `STATICFILES_STORAGE` setting — do not reintroduce it, it is silently ignored). `collectstatic` runs automatically on Railway during the build.

## Conventions

- Views are thin `APIView` subclasses; business logic (especially Claude calls) lives in helper modules (`claude.py`).
- Object ownership is enforced by filtering `Model.objects.filter(..., user=request.user)` and returning `404` for cross-user access (see `_get_session` in `apps.chat.views`). Never expose a `PermissionDenied` that leaks existence.
- Comments are reserved for non-obvious "why" — well-named code is the default documentation.
- The `migrations/` directories are committed and authoritative; run `makemigrations` for any model change.
