# NullBreach API

AI-powered cybersecurity assistant backend built with Django REST Framework and Claude.

## Stack

- Python 3.12 / Django 5.1.4 / Django REST Framework 3.15.2
- PostgreSQL via `dj-database-url` (falls back to SQLite for local dev if `DATABASE_URL` is unset)
- Simple JWT 5.3.1 — access (60 min) + refresh (7 days), rotation enabled, blacklist on logout/rotation
- Claude `claude-sonnet-4-20250514` via the Anthropic SDK (0.40.0)
- OpenAPI schema + Swagger UI via drf-spectacular 0.28.0
- Per-user rate limiting on Claude endpoints (DRF throttling)
- Request audit logging via `config.middleware.RequestAuditMiddleware`
- Static files served by WhiteNoise; deployable to Railway via `Procfile` (Gunicorn)

---

## Local setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/wavival/nullbreach-back.git
cd nullbreach-back
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in every value:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | yes | Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) |
| `DEBUG` | yes | `True` for local dev, `False` in production |
| `DATABASE_URL` | optional in dev | PostgreSQL connection string. If omitted, defaults to local `sqlite:///db.sqlite3` |
| `ANTHROPIC_API_KEY` | required in prod | Your Anthropic API key. Required when `DEBUG=False` (the app refuses to start otherwise) |
| `ALLOWED_HOSTS` | yes | Comma-separated hostnames (default: `localhost,127.0.0.1`) |
| `CORS_ALLOWED_ORIGINS` | yes | Comma-separated frontend origins (default: `http://localhost:5173`) |

### 3. Set up the database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run the development server

```bash
python manage.py runserver
```

### 5. Run the test suite

```bash
python manage.py test tests
```

Test suites live in `tests/`: `test_auth.py`, `test_chat.py`, `test_analyzer.py`.

---

## API reference

All endpoints are prefixed with `/api/`. Authenticated endpoints require:

```
Authorization: Bearer <access_token>
```

### Auth — `/api/auth/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register/` | No | Register a new user |
| POST | `/api/auth/login/` | No | Login, returns access + refresh tokens |
| POST | `/api/auth/refresh/` | No | Refresh access token (returns a rotated refresh token; the previous one is blacklisted) |
| POST | `/api/auth/logout/` | Yes | Blacklist a refresh token |
| GET | `/api/auth/me/` | Yes | Authenticated user info |

**Register request body:**
```json
{ "email": "user@example.com", "password": "secret123" }
```

**Register response (`201`):**
```json
{
  "user": { "id": 1, "email": "user@example.com", "date_joined": "2026-05-11T12:00:00Z" },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

**Login request body:**
```json
{ "email": "user@example.com", "password": "secret123" }
```

**Login response (`200`):**
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

**Logout request body:**
```json
{ "refresh": "<refresh_jwt>" }
```
Returns `204 No Content` on success.

---

### Chat — `/api/chat/`

| Method | Path | Auth | Throttle | Description |
|--------|------|------|----------|-------------|
| GET | `/api/chat/sessions/` | Yes | `user` (500/h) | List all sessions for the user |
| POST | `/api/chat/sessions/` | Yes | `user` (500/h) | Create a new chat session |
| DELETE | `/api/chat/sessions/{id}/` | Yes | `user` (500/h) | Delete a session and all its messages (cascade) |
| GET | `/api/chat/sessions/{id}/messages/` | Yes | `user` (500/h) | List messages in a session (oldest first) |
| POST | `/api/chat/sessions/{id}/messages/` | Yes | `claude_chat` (60/h) | Send a message, get Claude's reply |

**Send message request body** (`content`: 1–32,000 chars):
```json
{ "content": "How do I prevent SQL injection in Django?" }
```

**Send message response** (`201`, the persisted assistant message only):
```json
{
  "id": 42,
  "role": "assistant",
  "content": "To prevent SQL injection in Django...",
  "created_at": "2026-05-11T12:00:00Z"
}
```

The session is auto-titled from the first user message (truncated to 80 chars) if no title is set. A Claude API error returns `502 Bad Gateway`.

---

### Analyzer — `/api/analyzer/`

| Method | Path | Auth | Throttle | Description |
|--------|------|------|----------|-------------|
| POST | `/api/analyzer/scan/` | Yes | `claude_scan` (20/h) | Analyze a code snippet for OWASP Top 10 vulnerabilities |

**Request body** (`code`: 1–100,000 chars; `language` optional, defaults to `""`):
```json
{
  "code": "query = \"SELECT * FROM users WHERE id = \" + user_input",
  "language": "python"
}
```

**Response (`200`):**
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

`severity` is one of `critical | high | medium | low | info`. `risk_score` is an integer `0–100`. `line` may be `null`. If Claude's response cannot be parsed as JSON, the endpoint returns `502 Bad Gateway`.

---

### OpenAPI / Swagger

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/schema/` | No | OpenAPI 3 schema (YAML) |
| GET | `/api/docs/` | No | Swagger UI |

---

## Rate limits

Configured via DRF throttling in `config/settings.py`:

| Scope | Limit | Applies to |
|---|---|---|
| `user` | 500 / hour | All authenticated endpoints by default |
| `claude_chat` | 60 / hour | `POST /api/chat/sessions/{id}/messages/` |
| `claude_scan` | 20 / hour | `POST /api/analyzer/scan/` |

Throttled requests return `429 Too Many Requests`.

---

## Observability

`RequestAuditMiddleware` (`config/middleware.py`) logs every request via the `audit` logger at `INFO`:

```
<METHOD> <PATH> <STATUS> <DURATION_ms>ms
```

Logging is configured to stream to stdout (`console` handler), suitable for Railway / container log collectors.

---

## Production security

When `DEBUG=False` (and not running under `manage.py test`), `config/settings.py` enables:

- `SECURE_SSL_REDIRECT = True`
- `SECURE_HSTS_SECONDS = 31536000` with `INCLUDE_SUBDOMAINS` and `PRELOAD`
- `SESSION_COOKIE_SECURE = True`
- `CSRF_COOKIE_SECURE = True`

`ANTHROPIC_API_KEY` is also strictly required — the app raises `ImproperlyConfigured` at boot if it's unset.

---

## Deployment (Railway)

1. Create a new Railway project and add a PostgreSQL plugin.
2. Set all environment variables from `.env.example` in the Railway dashboard (`DEBUG=False`, real `SECRET_KEY`, real `ANTHROPIC_API_KEY`, production `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`).
3. Push to your linked repository — Railway will run `release: python manage.py migrate` then start Gunicorn via the `Procfile` (`web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`).

Static files are collected and served by WhiteNoise (`CompressedManifestStaticFilesStorage`).

---

## Admin panel

Available at `/admin/`. Create a superuser with `python manage.py createsuperuser`.

Registered models:

- `users.User` — custom email-only user model (`AUTH_USER_MODEL = "users.User"`)
- `chat.ChatSession` (with inline `Message` view)
- `chat.Message`
