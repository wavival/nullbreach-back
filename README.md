<h1 align="left">
  <img src="assets/icon.svg" width="32px" valign="middle">
  NullBreach • API
</h1>

![Banner principal](assets/banner.png)

> NullBreach is the backend for an AI cybersecurity assistant: authenticated users chat with Claude about security and submit code snippets for an OWASP Top 10 vulnerability scan. It ships production-hardened and deploys to Railway out of the box.

[![Live Demo](https://img.shields.io/badge/Live_Demo-wavival.dev/nullbreach-0F172A?style=for-the-badge&logo=vercel&logoColor=white)](https://wavival.dev/nullbreach)
[![API Docs](https://img.shields.io/badge/API_Docs-nullbreach--api.wavival.dev-0F172A?style=for-the-badge&logo=swagger&logoColor=white)](https://nullbreach-api.wavival.dev/api/docs/)
[![Frontend Repo](https://img.shields.io/badge/Frontend_Repo-nullbreach--web-0F172A?style=for-the-badge&logo=github&logoColor=white)](https://github.com/wavival/nullbreach-web)

## Table of contents

1. [Tech stack](#tech-stack)
2. [Features](#features)
3. [Quick start](#quick-start)
4. [Environment variables](#environment-variables)
5. [API reference](#api-reference)
6. [Database](#database)
7. [Testing](#testing)
8. [Development](#development)
9. [Deployment](#deployment)
10. [License](#license)
11. [Contact](#contact)

## Tech stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.12 |
| **Framework** | Django 5.1.4 + Django REST Framework 3.15.2 |
| **Database** | PostgreSQL (production), SQLite fallback for local dev |
| **Authentication** | JSON Web Tokens via `djangorestframework-simplejwt` 5.3.1 (access + refresh, rotation, blacklist) |
| **AI** | Claude `claude-haiku-4-5-20251001` via the official Anthropic Python SDK (`anthropic` 0.101.0) |
| **API docs** | OpenAPI 3 schema + Swagger UI + ReDoc via `drf-spectacular` 0.28.0 |
| **Rate limiting** | DRF throttling (per-user, per-scope) **plus** a DB-backed daily per-user limit (`apps/ratelimit`) |
| **Static files** | WhiteNoise (`CompressedManifestStaticFilesStorage`) |
| **WSGI server** | Gunicorn 23.0.0 |
| **CORS** | `django-cors-headers` 4.6.0 |
| **Config** | `django-environ` + `dj-database-url` |
| **Deployment** | Railway (`Procfile`-based) |

## Features

- **Authentication**, Email-only custom user model, registration with password validation, JWT login, token refresh with rotation, logout that blacklists the refresh token, and an authenticated `/me/` endpoint.
- **AI chat with persistent history**, Authenticated users create chat sessions and exchange messages with Claude. Full conversation history is persisted per session and replayed to Claude on each turn so context is preserved. Sessions are auto-titled from the first user message.
- **OWASP Top 10 analyzer**, Submit a code snippet and an optional language; Claude returns a structured JSON report of detected vulnerabilities (severity, line, description, recommendation), a summary, and a 0–100 risk score.
- **Per-endpoint rate limiting**, Two layers: DRF throttles on Claude-backed endpoints (`60/h` chat, `20/h` scan) plus a DB-backed **daily per-user limit** (10 chat messages/day, 5 analyzer scans/day) that persists across restarts and resets at UTC midnight. Exceeding the daily limit returns `429` with a `reset_at` timestamp.
- **Auto-generated API docs**, Swagger UI at `/api/docs/`, ReDoc at `/api/schema/redoc/`, and the OpenAPI 3 schema at `/api/schema/`, generated from view signatures and serializers via `drf-spectacular`.
- **Request audit logging**, Every request is logged with method, path, status, and duration via a custom middleware; every rate-limit check is logged for debugging.
- **Production hardening**, Trusts the `X-Forwarded-Proto` header so HTTPS is recognised behind Railway's proxy. When `DEBUG=False`, session and CSRF cookies are marked secure, and the app refuses to boot without `ANTHROPIC_API_KEY`. SSL redirection and HSTS are intentionally delegated to the platform proxy.
- **56 automated tests (91% coverage)**, Covering auth flows, chat ownership and persistence, analyzer validation, daily rate limiting, Claude error handling, and structured JSON logging (Claude is mocked).

## Quick start

### Prerequisites

- Python 3.12+
- PostgreSQL 14+ (optional for local dev, SQLite is used automatically if `DATABASE_URL` is unset)
- An [Anthropic API key](https://console.anthropic.com/) (only required in production; chat/analyzer endpoints won't work in dev without it either)

### 1. Clone and install

```bash
git clone https://github.com/wavival/nullbreach-api.git
cd nullbreach-api

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Then edit `.env`. At minimum you need a `SECRET_KEY` (generate one with the command in the env file) and an `ANTHROPIC_API_KEY` if you want chat or analyzer to work. See the [Environment variables](#environment-variables) section for the full list.

### 3. Migrate and create a superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run the dev server

```bash
python manage.py runserver
```

The API will be available at **http://localhost:8000/api/**

Interactive Swagger UI: **http://localhost:8000/api/docs/**

Django admin: **http://localhost:8000/admin/**

### Try it with curl

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"StrongPass123!"}'

# Login (save the access token from the response)
ACCESS=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"StrongPass123!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access'])")

# Create a chat session
curl -X POST http://localhost:8000/api/chat/sessions/ \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"title":"My first chat"}'
```

## Environment variables

All variables are loaded from a `.env` file in the project root (via `django-environ`). The `.env.example` file in the repo contains commented examples for every variable.

| Variable | Required | Description | Example |
|---|---|---|---|
| `SECRET_KEY` | **Always** | Django cryptographic key. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. | `django-insecure-...` (50+ chars) |
| `DEBUG` | Always | `True` in dev, `False` in prod. When `False`, the app enforces HTTPS, secure cookies, and HSTS, and refuses to boot without `ANTHROPIC_API_KEY`. | `True` / `False` |
| `DATABASE_URL` | Optional in dev / **required in prod** | PostgreSQL connection string. If omitted in dev, Django uses local `sqlite:///db.sqlite3`. | `postgresql://user:pass@host:5432/db` |
| `ANTHROPIC_API_KEY` | **Required in prod** + needed for chat/analyzer to function | Claude API key from [console.anthropic.com](https://console.anthropic.com/) → Settings → API Keys. | `sk-ant-api03-...` |
| `ALLOWED_HOSTS` | Always | Comma-separated list of hostnames Django will accept. | `localhost,127.0.0.1,api.example.com` |
| `CORS_ALLOWED_ORIGINS` | Always | Comma-separated frontend origins allowed to call the API. | `http://localhost:5173,https://wavival.dev` |
| `CSRF_TRUSTED_ORIGINS` | Optional | Comma-separated trusted origins (scheme required) for the Django admin behind a TLS proxy. Defaults to `CORS_ALLOWED_ORIGINS`. | `https://nullbreach-api.up.railway.app` |
| `CHAT_DAILY_LIMIT` | Optional | Max chat messages per user per day. Defaults to `10`. | `10` |
| `ANALYZER_DAILY_LIMIT` | Optional | Max analyzer scans per user per day. Defaults to `5`. | `5` |
| `REDIS_URL` | Optional | If set, DRF throttle counters use Redis. Otherwise the DB cache table is used (created by the `release` step on Railway). | `redis://...` |
| `SECURE_HSTS_SECONDS` | Optional (prod) | Override the 1-year HSTS default. Set to `0` to disable HSTS temporarily. | `31536000` |

## API reference

All endpoints are prefixed with `/api/`. Authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

Interactive documentation is auto-generated: Swagger UI at `/api/docs/`, ReDoc at `/api/schema/redoc/`, and the raw OpenAPI 3 schema at `/api/schema/`.

### Auth, `/api/auth/`

| Method | Path | Auth | Limits | Description |
|--------|------|:----:|--------|-------------|
| `POST` | `/api/auth/register/` | No | `auth` (10/min) | Register a new user; returns a generic `202`, silent on duplicate email |
| `POST` | `/api/auth/login/` | No | `auth` (10/min) | Login; returns access + refresh tokens |
| `POST` | `/api/auth/refresh/` | No | `auth` (10/min) | Rotate refresh token; previous is blacklisted |
| `POST` | `/api/auth/logout/` | Yes | `user` (500/h) | Blacklist a refresh token |
| `GET` | `/api/auth/me/` | Yes | `user` (500/h) | Return the authenticated user |

`register`, `login`, and `refresh` are throttled per IP by the `auth` scope (`10/min`) to slow credential stuffing and registration enumeration. Any other unauthenticated request falls under the global `anon` scope (`60/h`).

**Register**, `POST /api/auth/register/`

Request:
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```
Response (`202`):
```json
{ "detail": "Registration accepted. If this email is new, your account is now active." }
```
The response is intentionally generic and identical whether the email is new or already registered, this prevents account enumeration. No tokens are returned, genuine new users obtain tokens by POSTing to `/api/auth/login/` immediately afterwards.
Errors: `400` on an invalid email format or a password that fails Django's validators. A duplicate email is **not** an error, it returns the same `202`.

**Login**, `POST /api/auth/login/`

Request:
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```
Response (`200`): `{ "access": "<jwt>", "refresh": "<jwt>" }`. Errors: `401` on bad credentials.

**Refresh**, `POST /api/auth/refresh/`, Request `{ "refresh": "<jwt>" }` → `{ "access": "<jwt>", "refresh": "<jwt>" }` (new refresh; old one is blacklisted).

**Logout**, `POST /api/auth/logout/`, Request `{ "refresh": "<jwt>" }` → `204 No Content`. Errors: `400` if the token is missing or invalid.

**Me**, `GET /api/auth/me/`, Response (`200`): `{ "id": 1, "email": "...", "date_joined": "..." }`. Errors: `401` if unauthenticated.

### Chat, `/api/chat/`

| Method | Path | Auth | Limits | Description |
|--------|------|:----:|--------|-------------|
| `GET` | `/api/chat/sessions/` | Yes | `user` (500/h) | List the caller's chat sessions |
| `POST` | `/api/chat/sessions/` | Yes | `user` (500/h) | Create a new session |
| `PATCH` | `/api/chat/sessions/{id}/` | Yes | `user` (500/h) | Update a session (e.g. rename its title) |
| `DELETE` | `/api/chat/sessions/{id}/` | Yes | `user` (500/h) | Delete a session and all its messages (cascade) |
| `GET` | `/api/chat/sessions/{id}/messages/` | Yes | `user` (500/h) | List messages in a session (oldest first) |
| `POST` | `/api/chat/sessions/{id}/messages/` | Yes | `claude_chat` (60/h) + **10/day** | Send a message; returns Claude's reply |

**Send message**, `POST /api/chat/sessions/{id}/messages/`

Request (`content`: 1–32,000 chars):
```json
{ "content": "How do I prevent SQL injection in Django?" }
```
Response (`201`, the persisted assistant message):
```json
{
  "id": 42,
  "role": "assistant",
  "content": "To prevent SQL injection in Django, always use the ORM or parameterized queries...",
  "created_at": "2026-05-11T12:00:00Z"
}
```
The session auto-titles itself from the first user message (truncated to 80 chars) if no title is set.
Errors: `404` if the session doesn't belong to the caller, `502` if the Claude API fails, `429` when throttled or when the daily limit is reached (see [Daily rate limit](#daily-rate-limit)).

### Analyzer, `/api/analyzer/`

| Method | Path | Auth | Limits | Description |
|--------|------|:----:|--------|-------------|
| `POST` | `/api/analyzer/scan/` | Yes | `claude_scan` (20/h) + **5/day** | OWASP Top 10 vulnerability analysis of a code snippet |

**Scan**, `POST /api/analyzer/scan/`

Request (`code`: 1–100,000 chars; `language` optional, defaults to `""`):
```json
{
  "code": "query = \"SELECT * FROM users WHERE id = \" + user_input",
  "language": "python"
}
```
Response (`200`):
```json
{
  "vulnerabilities": [
    {
      "id": "A03:2021",
      "name": "Injection",
      "severity": "critical",
      "line": 1,
      "description": "String concatenation used in a raw SQL query allows SQL injection.",
      "recommendation": "Use parameterized queries or Django ORM."
    }
  ],
  "summary": "The snippet is critically vulnerable to SQL injection.",
  "risk_score": 90
}
```
- `severity` ∈ `critical | high | medium | low | info`
- `line` may be `null`
- `risk_score` is an integer `0–100`

Errors: `400` on empty/missing code, `502` if Claude fails or returns unparseable JSON, `429` when throttled or when the daily limit is reached.

### Daily rate limit

Claude-backed endpoints enforce a DB-backed daily per-user limit on top of DRF throttling. When the limit is reached the endpoint responds `429`:

```json
{
  "detail": "Daily limit reached. Try again tomorrow.",
  "reset_at": "2026-05-15T00:00:00Z"
}
```

`reset_at` is the next UTC midnight, when the counter resets. Limits are configurable via `CHAT_DAILY_LIMIT` and `ANALYZER_DAILY_LIMIT`.

### Docs and admin

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/api/schema/` | No | OpenAPI 3 schema (YAML) |
| `GET` | `/api/docs/` | No | Interactive Swagger UI |
| `GET` | `/api/schema/redoc/` | No | ReDoc documentation |
| `*` | `/admin/` | Staff | Django admin (login required) |

### Status codes used

| Code | Meaning |
|---|---|
| `200` | OK |
| `201` | Created (create session, send message) |
| `202` | Accepted (register, response is generic and identical for new and duplicate emails) |
| `204` | No Content (logout, delete session) |
| `400` | Bad request (validation error, missing field) |
| `401` | Unauthenticated / invalid token |
| `404` | Resource not found or not owned by the caller |
| `429` | Rate limited (DRF throttle or daily limit exceeded) |
| `502` | Bad Gateway (Claude API error or unparseable response) |

## Database

### `users.User`, custom user model

Email is the unique identifier (`AUTH_USER_MODEL = "users.User"`); there is no `username` field.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAuto PK | |
| `email` | EmailField | unique, `USERNAME_FIELD` |
| `password` | hashed | managed by Django |
| `is_active` | bool | default `True` |
| `is_staff` | bool | default `False` |
| `date_joined` | datetime | `auto_now_add` |
| `is_superuser`, `groups`, `user_permissions` | various | from `PermissionsMixin` |

### `chat.ChatSession`

| Field | Type | Notes |
|---|---|---|
| `id` | BigAuto PK | |
| `user` | FK → `User` | `on_delete=CASCADE`, `related_name="chat_sessions"` |
| `title` | CharField(255) | blank by default; auto-set from first user message |
| `created_at` | datetime | `auto_now_add` |
| `updated_at` | datetime | `auto_now` |

Default ordering: `-updated_at` (most recent first).

### `chat.Message`

| Field | Type | Notes |
|---|---|---|
| `id` | BigAuto PK | |
| `session` | FK → `ChatSession` | `on_delete=CASCADE`, `related_name="messages"` |
| `role` | CharField(10) | choices: `user`, `assistant` |
| `content` | TextField | |
| `created_at` | datetime | `auto_now_add` |

Default ordering: `created_at` (oldest first).

### `ratelimit.RateLimit`

DB-backed daily request counter, one row per `(user, endpoint)`.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAuto PK | |
| `user` | FK → `User` | `on_delete=CASCADE`, `related_name="rate_limits"` |
| `endpoint` | CharField(64) | logical endpoint key (`chat_messages`, `analyzer_scan`) |
| `count` | PositiveInteger | requests in the current window; default `0` |
| `reset_at` | datetime | next UTC midnight; counter resets once passed |
| `created_at` / `updated_at` | datetime | `auto_now_add` / `auto_now` |

Unique constraint on `(user, endpoint)`, its index also serves the lookup.

### Relationships

```
User ──< ChatSession ──< Message
User ──< RateLimit
 1:N
```

Deleting a `User` cascades to all their sessions, messages, and rate-limit rows; deleting a session cascades to its messages. The analyzer is stateless and does not persist anything beyond its rate-limit counter.

## Testing

The test suite covers the critical paths of each app. Claude is mocked in chat and analyzer tests so the suite runs offline and deterministically.

### Run all tests

```bash
python manage.py test tests
```

Expected: **56 tests passing, 91% coverage**.

### Run a specific file

```bash
python manage.py test tests.test_auth
python manage.py test tests.test_chat
python manage.py test tests.test_analyzer
python manage.py test tests.test_ratelimit
```

### Coverage report

```bash
coverage run --source=apps,config manage.py test tests
coverage report
```

`pyproject.toml` configures `coverage`'s source paths and omit rules, and sets `fail_under = 80`.

### What's covered

| File | Tests | Coverage |
|---|---|---|
| `tests/test_auth.py` | 17 | Register success returns generic 202, duplicate email silent, response body identical for new and duplicate, weak password, invalid email format; login success / wrong password / unknown email; `/me/` authenticated / unauthenticated / invalid token; logout blacklists refresh / missing refresh / requires auth; refresh returns a new token pair, old refresh blacklisted after rotation; login brute force returns 429 |
| `tests/test_chat.py` | 14 | Create session, list only own sessions, delete session, deleting other user's session returns 404, patch session title, patching other user's session returns 404, unauthenticated returns 401, list messages (empty + ordered), send message persists both sides and calls Claude, auto-title on first message, cross-user message send returns 404, rolls back user message on Claude failure, chat throttle returns 429 after the limit |
| `tests/test_analyzer.py` | 8 | Authenticated scan returns structured result, default language, unauthenticated returns 401, empty code returns 400, missing code returns 400, Claude API error returns 502, malformed JSON returns 502, unexpected response shape returns 502 |
| `tests/test_ratelimit.py` | 7 | Requests succeed up to the daily limit, the request past the limit returns 429 with a clear payload (`reset_at` serialised as an ISO 8601 `Z` string), the counter resets after UTC midnight, limits are tracked per `(user, endpoint)`, a chat limit does not block the analyzer, for both chat and analyzer |
| `tests/test_claude_errors.py` | 6 | `handle_claude_error` maps Anthropic error subclasses to DRF responses (401/404/429/502), preserves `Retry-After` (and works without it), ignores non-Anthropic exceptions |
| `tests/test_log_formatter.py` | 4 | `JSONFormatter` emits one JSON object per line; flattens exc_info; merges `extra={...}` fields; reserved fields not duplicated |

## Development

### Folder structure

```
nullbreach-api/
├── apps/
│   ├── users/           # Custom email-only user model + JWT auth views
│   │   ├── models.py    # User, UserManager
│   │   ├── serializers.py
│   │   ├── views.py     # Register, Login, Refresh, Logout, Me
│   │   ├── urls.py
│   │   └── admin.py
│   ├── chat/            # Chat sessions + messages backed by Claude
│   │   ├── models.py    # ChatSession, Message
│   │   ├── claude.py    # Claude client + system prompt
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── admin.py
│   ├── analyzer/        # OWASP Top 10 vulnerability scanner
│   │   ├── claude.py    # JSON-only system prompt for Claude
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── ratelimit/       # DB-backed daily per-user rate limiting
│   │   ├── models.py    # RateLimit
│   │   ├── decorators.py # @check_rate_limit
│   │   └── admin.py
│   ├── throttles.py     # ClaudeChatThrottle, ClaudeScanThrottle, AuthAnonThrottle
│   └── claude_errors.py # handle_claude_error
├── config/
│   ├── settings.py      # All settings, DRF + JWT + throttling + logging
│   ├── urls.py          # Root router (mounts apps and OpenAPI views)
│   ├── middleware.py    # RequestAuditMiddleware
│   ├── log_formatter.py # JSONFormatter
│   ├── wsgi.py
│   └── asgi.py
├── tests/
│   ├── test_auth.py
│   ├── test_chat.py
│   ├── test_analyzer.py
│   ├── test_ratelimit.py
│   ├── test_claude_errors.py
│   └── test_log_formatter.py
├── .env.example
├── .pre-commit-config.yaml  # Black + isort + Ruff hooks
├── .python-version          # Python runtime pin (3.12) for the Railway build
├── CLAUDE.md                # Guidance for AI coding assistants
├── manage.py
├── Procfile
├── pyproject.toml           # Black, isort, Ruff, coverage config
├── requirements.txt
├── requirements-dev.txt
└── LICENSE
```

### Adding a new endpoint

1. **Pick or create an app** under `apps/`. For a brand-new module:
   ```bash
   python manage.py startapp my_module apps/my_module
   ```
   Add `"apps.my_module"` to `INSTALLED_APPS` in `config/settings.py`.
2. **Define your model(s)** in `apps/my_module/models.py` and run `makemigrations` + `migrate`.
3. **Write a serializer** in `apps/my_module/serializers.py` (use `ModelSerializer` for CRUD, `Serializer` for custom payloads).
4. **Write the view** in `apps/my_module/views.py`. Decorate with `@extend_schema(...)` so it appears correctly in Swagger. Set `permission_classes = [IsAuthenticated]` unless the endpoint is public.
5. **Wire the URL** in `apps/my_module/urls.py` and include it from `config/urls.py` under `/api/<module>/`.
6. **If the view calls Claude or another expensive backend**, define a custom throttle scope in `apps/throttles.py` and set `throttle_classes = [...]` on the view; add the corresponding rate to `DEFAULT_THROTTLE_RATES` in `config/settings.py`. For a daily per-user cap, apply `@check_rate_limit(...)` from `apps/ratelimit/decorators.py` and add a key to `RATE_LIMITS`.
7. **Write tests** in `tests/test_<module>.py`. Mock external calls (`unittest.mock.patch`) so tests stay offline and deterministic.

### Conventions

- **Apps under `apps/`**, not at the project root. The package is imported as `apps.<name>`.
- **One file per concern**: models, serializers, views, urls, admin. Keep view files thin, push business logic into helpers (e.g. `claude.py` in chat and analyzer).
- **DRF `APIView` + serializers** is the default, viewsets/routers are only used if the resource truly maps to standard CRUD.
- **Throttles per scope**: any Claude-backed view gets its own scope and rate.
- **Permissions default to `IsAuthenticated`** (set globally in `REST_FRAMEWORK`). Override with `permission_classes = [AllowAny]` only where strictly necessary.
- **Tests mock Claude** via `unittest.mock.patch("apps.<app>.views.<func>")`, never hit the live API from the suite.
- **English throughout**, code, comments, docstrings, and documentation are all in English.
- **Comments are reserved for non-obvious "why"**, well-named code is the default documentation.
- **No hardcoded config**, secrets and tunables come from environment variables (see `.env.example`).

### Linting and formatting

Code style is enforced by **Black**, **isort**, and **Ruff** (line length 100), all configured in `pyproject.toml`. `.pre-commit-config.yaml` wires them as pre-commit hooks alongside trailing-whitespace, end-of-file, and YAML checks.

```bash
pip install -r requirements-dev.txt
pre-commit install            # run the hooks on every commit
pre-commit run --all-files    # run them across the whole repo on demand
```

## Deployment

The repo is configured to deploy out of the box on [Railway](https://railway.app/) via the `Procfile`:

```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2
release: python manage.py migrate && python manage.py createcachetable
```

> **Why `createcachetable`?** The default cache backend in production is `DatabaseCache` (used by DRF throttling to share counters across Gunicorn workers). The release step creates the `django_cache` table once; subsequent deploys are no-ops. Set `REDIS_URL` if you'd rather use Redis.

### Steps

1. **Create a Railway project** and link it to your fork of this repository.
2. **Add a PostgreSQL plugin** to the project. Railway injects a `DATABASE_URL` variable automatically.
3. **Set the remaining environment variables** in Railway's dashboard:
   - `SECRET_KEY`, generated with the snippet from `.env.example`
   - `DEBUG=False`
   - `ANTHROPIC_API_KEY`, from [console.anthropic.com](https://console.anthropic.com/)
   - `ALLOWED_HOSTS`, your Railway domain (e.g. `nullbreach-api.up.railway.app`) plus any custom domain
   - `CORS_ALLOWED_ORIGINS`, your frontend origin(s) (e.g. `https://wavival.dev`)
   - `CSRF_TRUSTED_ORIGINS`, your Railway domain (with scheme) if you use the Django admin
   - *(optional)* `CHAT_DAILY_LIMIT`, `ANALYZER_DAILY_LIMIT` to override the daily rate limits
4. **Deploy.** Railway runs the `release` command first (`migrate` + `createcachetable`), then starts Gunicorn. Static files are collected and served by WhiteNoise with manifest-based caching.
5. **Create a superuser** on the running service:
   ```bash
   railway run python manage.py createsuperuser
   ```

### Test the production build locally

```bash
DEBUG=False SECRET_KEY=... ANTHROPIC_API_KEY=... DATABASE_URL=... \
  gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

## License

This project is licensed under the **MIT License**, with the following clarification:

- **Clone**: You can clone this repository freely
- **Fork**: You can fork and create your own version
- **Contribute**: Pull requests and contributions are welcome
- **Learn**: Use this code to study and learn software architecture
- **Modify**: Adapt the code to your needs
- **Attribution**: Please credit the original author (Valentina Ramírez / @wavival)

This is **not** a commercial product. It's an educational resource demonstrating 
backend security, API design, and full-stack development practices. See the [LICENSE](./LICENSE) file for the full text.

Copyright © 2026 Valentina Ramírez.

## Contact

![Banner principal](assets/footer.png)

<h3 align="left">
  <img src="assets/logo-w.png" width="48px" valign="middle">
  Valentina Ramírez • @wavival
</h3>

> Thanks for getting here. Let's build great things.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-wavival-407bff?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/wavival)
[![Instagram](https://img.shields.io/badge/Instagram-@wavival-407bff?style=for-the-badge&logo=instagram&logoColor=white)](https://www.instagram.com/wavival)
[![Email](https://img.shields.io/badge/Email-wavival.dev@luminaw.co-407bff?style=for-the-badge&logo=gmail&logoColor=white)](mailto:wavival.dev@luminaw.co)
