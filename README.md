# NullBreach API

> AI-powered cybersecurity assistant backend — secure chat with Claude and OWASP Top 10 vulnerability analysis, built with Django REST Framework.

![Status](https://img.shields.io/badge/status-✓%20Complete%20%26%20Tested-success)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.1.4-092E20?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.15.2-A30000)
![Tests](https://img.shields.io/badge/tests-28%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

**Live demo:** [wavival.dev/nullbreach](https://wavival.dev/nullbreach)
**Frontend repo:** [github.com/wavival/nullbreach-front](https://github.com/wavival/nullbreach-front)
**Backend repo:** [github.com/wavival/nullbreach-back](https://github.com/wavival/nullbreach-back)

---

## Table of contents

1. [Tech stack](#tech-stack)
2. [Features](#features)
3. [Quick start](#quick-start)
4. [Environment variables](#environment-variables)
5. [API reference](#api-reference)
6. [Database](#database)
7. [Testing](#testing)
8. [Deployment (Railway)](#deployment-railway)
9. [Development](#development)
10. [License](#license)
11. [Contact](#contact)

---

## Tech stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.12 |
| **Framework** | Django 5.1.4 + Django REST Framework 3.15.2 |
| **Database** | PostgreSQL (production) — SQLite fallback for local dev |
| **Authentication** | JSON Web Tokens via `djangorestframework-simplejwt` 5.3.1 (access + refresh, rotation, blacklist) |
| **AI** | Claude `claude-sonnet-4-20250514` via the official Anthropic Python SDK (`anthropic` 0.40.0) |
| **API docs** | OpenAPI 3 schema + Swagger UI via `drf-spectacular` 0.28.0 |
| **Rate limiting** | Built-in DRF throttling (per-user, per-scope) |
| **Static files** | WhiteNoise (`CompressedManifestStaticFilesStorage`) |
| **WSGI server** | Gunicorn 23.0.0 |
| **CORS** | `django-cors-headers` 4.6.0 |
| **Config** | `python-dotenv` + `dj-database-url` |
| **Deployment** | Railway (`Procfile`-based) |

---

## Features

- **Authentication** — Email-only custom user model, registration with password validation, JWT login, token refresh with rotation, logout that blacklists the refresh token, and an authenticated `/me/` endpoint.
- **AI chat with persistent history** — Authenticated users create chat sessions and exchange messages with Claude. Full conversation history is persisted per session and replayed to Claude on each turn so context is preserved. Sessions are auto-titled from the first user message.
- **OWASP Top 10 analyzer** — Submit a code snippet and an optional language; Claude returns a structured JSON report of detected vulnerabilities (severity, line, description, recommendation), a summary, and a 0–100 risk score.
- **Per-endpoint rate limiting** — Strict throttles on Claude-backed endpoints (`60/h` chat, `20/h` scan) and a generous default for everything else (`500/h`).
- **Auto-generated API docs** — Swagger UI at `/api/docs/` and OpenAPI 3 schema at `/api/schema/`, generated from view signatures and serializers via `drf-spectacular`.
- **Request audit logging** — Every request is logged with method, path, status, and duration via a custom middleware.
- **Production hardening** — When `DEBUG=False`: HTTPS redirect, HSTS preload, secure session and CSRF cookies, and a startup check that refuses to boot without `ANTHROPIC_API_KEY`.
- **28 automated tests** — Covering auth flows, chat ownership and persistence, analyzer validation, and Claude error handling (Claude is mocked).

---

## Quick start

### Prerequisites

- Python 3.12+
- PostgreSQL 14+ (optional for local dev — SQLite is used automatically if `DATABASE_URL` is unset)
- An [Anthropic API key](https://console.anthropic.com/) (only required in production; chat/analyzer endpoints won't work in dev without it either)

### 1. Clone and install

```bash
git clone https://github.com/wavival/nullbreach-back.git
cd nullbreach-back

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

The API will be available at **http://localhost:8000/api/**.
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

---

## Environment variables

All variables are loaded from a `.env` file in the project root (via `python-dotenv`). The `.env.example` file in the repo contains commented examples for all six.

| Variable | Required | Example | How to get it |
|---|---|---|---|
| `SECRET_KEY` | **Always** | `django-insecure-...` (50+ chars) | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | Always | `True` (dev) / `False` (prod) | Set manually. When `False`, the app enforces HTTPS, secure cookies, and HSTS, and refuses to boot without `ANTHROPIC_API_KEY`. |
| `DATABASE_URL` | Optional in dev / **required in prod** | `postgresql://user:pass@host:5432/db` | From your Postgres provider (Railway, Supabase, Neon, local Postgres, etc.). If omitted in dev, Django uses local `sqlite:///db.sqlite3`. |
| `ANTHROPIC_API_KEY` | **Required in prod** + needed for chat/analyzer to function | `sk-ant-api03-...` | [console.anthropic.com](https://console.anthropic.com/) → **Settings → API Keys → Create Key**. |
| `ALLOWED_HOSTS` | Always | `localhost,127.0.0.1,api.example.com` | Comma-separated list of hostnames Django will accept. |
| `CORS_ALLOWED_ORIGINS` | Always | `http://localhost:5173,https://wavival.dev` | Comma-separated list of frontend origins allowed to call the API. |

---

## API reference

All endpoints are prefixed with `/api/`. Authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

Interactive documentation is auto-generated and available at `/api/docs/` (Swagger UI). The raw OpenAPI 3 schema is at `/api/schema/`.

### Auth — `/api/auth/`

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `POST` | `/api/auth/register/` | No | Register a new user; returns tokens |
| `POST` | `/api/auth/login/` | No | Login; returns access + refresh tokens |
| `POST` | `/api/auth/refresh/` | No | Rotate refresh token; previous is blacklisted |
| `POST` | `/api/auth/logout/` | Yes | Blacklist a refresh token |
| `GET` | `/api/auth/me/` | Yes | Return the authenticated user |

**Register** — `POST /api/auth/register/`

Request:
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```
Response (`201`):
```json
{
  "user": { "id": 1, "email": "user@example.com", "date_joined": "2026-05-11T12:00:00Z" },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```
Errors: `400` on duplicate email or password that fails Django's validators.

**Login** — `POST /api/auth/login/`

Request:
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```
Response (`200`):
```json
{ "access": "<jwt>", "refresh": "<jwt>" }
```
Errors: `401` on bad credentials.

**Refresh** — `POST /api/auth/refresh/`

Request: `{ "refresh": "<jwt>" }` → Response (`200`): `{ "access": "<jwt>", "refresh": "<jwt>" }` (new refresh; old one is blacklisted).

**Logout** — `POST /api/auth/logout/`

Request: `{ "refresh": "<jwt>" }` → `204 No Content`. Errors: `400` if the token is missing or invalid.

**Me** — `GET /api/auth/me/`

Response (`200`): `{ "id": 1, "email": "...", "date_joined": "..." }`. Errors: `401` if unauthenticated.

---

### Chat — `/api/chat/`

| Method | Path | Auth | Throttle | Description |
|--------|------|:----:|----------|-------------|
| `GET` | `/api/chat/sessions/` | Yes | `user` (500/h) | List the caller's chat sessions |
| `POST` | `/api/chat/sessions/` | Yes | `user` (500/h) | Create a new session |
| `DELETE` | `/api/chat/sessions/{id}/` | Yes | `user` (500/h) | Delete a session and all its messages (cascade) |
| `GET` | `/api/chat/sessions/{id}/messages/` | Yes | `user` (500/h) | List messages in a session (oldest first) |
| `POST` | `/api/chat/sessions/{id}/messages/` | Yes | `claude_chat` (60/h) | Send a message; returns Claude's reply |

**Send message** — `POST /api/chat/sessions/{id}/messages/`

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
The session auto-titles itself from the first user message (truncated to 80 chars) if no title is set. Errors: `404` if the session doesn't belong to the caller, `502` if the Claude API fails, `429` when throttled.

---

### Analyzer — `/api/analyzer/`

| Method | Path | Auth | Throttle | Description |
|--------|------|:----:|----------|-------------|
| `POST` | `/api/analyzer/scan/` | Yes | `claude_scan` (20/h) | OWASP Top 10 vulnerability analysis of a code snippet |

**Scan** — `POST /api/analyzer/scan/`

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

Errors: `400` on empty/missing code, `502` if Claude fails or returns unparseable JSON, `429` when throttled.

---

### Docs and admin

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET` | `/api/schema/` | No | OpenAPI 3 schema (YAML) |
| `GET` | `/api/docs/` | No | Interactive Swagger UI |
| `*` | `/admin/` | Staff | Django admin (login required) |

---

### Status codes used

| Code | Meaning |
|---|---|
| `200` | OK |
| `201` | Created (register, create session, send message, etc.) |
| `204` | No Content (logout, delete session) |
| `400` | Bad request (validation error, missing field) |
| `401` | Unauthenticated / invalid token |
| `404` | Resource not found or not owned by the caller |
| `429` | Throttled (rate limit exceeded) |
| `502` | Bad Gateway (Claude API error or unparseable response) |

---

## Database

### `users.User` — custom user model

Email is the unique identifier (`AUTH_USER_MODEL = "users.User"`); there is no `username` field.

| Field | Type | Notes |
|---|---|---|
| `id` | BigAuto PK | |
| `email` | EmailField | unique, `USERNAME_FIELD` |
| `password` | hashed | managed by Django |
| `is_active` | bool | default `True` |
| `is_staff` | bool | default `False` |
| `date_joined` | datetime | `auto_now_add` |
| `is_superuser`, `groups`, `user_permissions` | — | from `PermissionsMixin` |

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

### Relationships

```
User ──< ChatSession ──< Message
 1:N         1:N
```

Deleting a `User` cascades to all their sessions; deleting a session cascades to all its messages. The analyzer is stateless and does not persist anything.

---

## Testing

The test suite covers the critical paths of each app. Claude is mocked in chat and analyzer tests so the suite runs offline and deterministically.

### Run all tests

```bash
python manage.py test tests
```

Expected: **28 tests passing**.

### Run a specific file

```bash
python manage.py test tests.test_auth
python manage.py test tests.test_chat
python manage.py test tests.test_analyzer
```

### What's covered

| File | Tests | Coverage |
|---|---|---|
| `tests/test_auth.py` | 12 | Register success / duplicate email / weak password; login success / wrong password / unknown email; `/me/` authenticated / unauthenticated / invalid token; logout blacklists refresh / missing refresh / requires auth |
| `tests/test_chat.py` | 10 | Create session, list only own sessions, delete session, deleting other user's session returns 404, unauthenticated → 401, list messages (empty + ordered), send message persists both sides and calls Claude, auto-title on first message, cross-user message send returns 404 |
| `tests/test_analyzer.py` | 6 | Authenticated scan returns structured result, default language, unauthenticated → 401, empty code → 400, missing code → 400, Claude API error → 502 |

---

## Deployment (Railway)

The repo is configured to deploy out of the box on [Railway](https://railway.app/) via the `Procfile`:

```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
release: python manage.py migrate
```

### Steps

1. **Create a Railway project** and link it to your fork of this repository.
2. **Add a PostgreSQL plugin** to the project. Railway will inject a `DATABASE_URL` variable automatically.
3. **Set the remaining environment variables** in Railway's dashboard:
   - `SECRET_KEY` — generated with the snippet from `.env.example`
   - `DEBUG=False`
   - `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com/)
   - `ALLOWED_HOSTS` — your Railway domain (e.g. `nullbreach-back.up.railway.app`) plus any custom domain
   - `CORS_ALLOWED_ORIGINS` — your frontend origin(s) (e.g. `https://wavival.dev`)
4. **Deploy.** Railway runs the `release` command first (`migrate`), then starts Gunicorn. Static files are collected and served by WhiteNoise with manifest-based caching.
5. **Create a superuser** on the running service:
   ```bash
   railway run python manage.py createsuperuser
   ```

---

## Development

### Folder structure

```
nullbreach-back/
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
│   └── throttles.py     # ClaudeChatThrottle, ClaudeScanThrottle
├── config/
│   ├── settings.py      # All settings, DRF + JWT + throttling + logging
│   ├── urls.py          # Root router (mounts apps and OpenAPI views)
│   ├── middleware.py    # RequestAuditMiddleware
│   ├── wsgi.py
│   └── asgi.py
├── tests/
│   ├── test_auth.py
│   ├── test_chat.py
│   └── test_analyzer.py
├── .env.example
├── manage.py
├── Procfile
├── requirements.txt
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
6. **If the view calls Claude or another expensive backend**, define a custom throttle scope in `apps/throttles.py` and set `throttle_classes = [...]` on the view; add the corresponding rate to `DEFAULT_THROTTLE_RATES` in `config/settings.py`.
7. **Write tests** in `tests/test_<module>.py`. Mock external calls (`unittest.mock.patch`) so tests stay offline and deterministic.

### Conventions

- **Apps under `apps/`**, not at the project root. The package is imported as `apps.<name>`.
- **One file per concern**: models, serializers, views, urls, admin. Keep view files thin — push business logic into helpers (e.g. `claude.py` in chat and analyzer).
- **DRF `APIView` + serializers** is the default — viewsets/routers are only used if the resource truly maps to standard CRUD.
- **Throttles per scope**: any Claude-backed view gets its own scope and rate.
- **Permissions default to `IsAuthenticated`** (set globally in `REST_FRAMEWORK`). Override with `permission_classes = [AllowAny]` only where strictly necessary.
- **Tests mock Claude** via `unittest.mock.patch("apps.<app>.views.<func>")` — never hit the live API from the suite.
- **Comments are reserved for non-obvious "why"** — well-named code is the default documentation.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](./LICENSE) file for the full text.

---

## Contact

**Valentina Ramírez**

- Portfolio — [wavival.dev](https://wavival.dev)
- GitHub — [github.com/wavival](https://github.com/wavival)
- LinkedIn — [linkedin.com/in/wavival](https://www.linkedin.com/in/wavival/)
- Email — [wavival.dev@luminaw.co](mailto:wavival.dev@luminaw.co)
