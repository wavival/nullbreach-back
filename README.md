# NullBreach API

AI-powered cybersecurity assistant backend built with Django REST Framework and Claude.

## Stack

- Python 3.12 / Django 5.x / Django REST Framework
- PostgreSQL
- Simple JWT (access + refresh tokens, blacklist on logout)
- Claude `claude-sonnet-4-20250514` via the Anthropic SDK
- Deployable to Railway via `Procfile`

---

## Local setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd nullbreach-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in every value:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) |
| `DEBUG` | `True` for local dev, `False` in production |
| `DATABASE_URL` | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins |

### 3. Set up the database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run the development server

```bash
python manage.py runserver
```

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
| POST | `/api/auth/refresh/` | No | Refresh access token |
| POST | `/api/auth/logout/` | Yes | Blacklist refresh token |
| GET | `/api/auth/me/` | Yes | Authenticated user info |

**Register / Login request body:**
```json
{ "email": "user@example.com", "password": "secret123" }
```

**Login / Register response:**
```json
{
  "user": { "id": 1, "email": "user@example.com", "date_joined": "..." },
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

---

### Chat — `/api/chat/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/chat/sessions/` | Yes | List all sessions for the user |
| POST | `/api/chat/sessions/` | Yes | Create a new chat session |
| DELETE | `/api/chat/sessions/{id}/` | Yes | Delete a session and all its messages |
| GET | `/api/chat/sessions/{id}/messages/` | Yes | List messages in a session |
| POST | `/api/chat/sessions/{id}/messages/` | Yes | Send a message, get Claude's reply |

**Send message request body:**
```json
{ "content": "How do I prevent SQL injection in Django?" }
```

**Send message response** (the assistant message):
```json
{
  "id": 42,
  "role": "assistant",
  "content": "To prevent SQL injection in Django...",
  "created_at": "2026-04-15T12:00:00Z"
}
```

---

### Analyzer — `/api/analyzer/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/analyzer/scan/` | Yes | Analyze a code snippet for OWASP Top 10 vulnerabilities |

**Request body:**
```json
{
  "code": "SELECT * FROM users WHERE id = " + user_input,
  "language": "python"
}
```

**Response:**
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

---

## Deployment (Railway)

1. Create a new Railway project and add a PostgreSQL plugin.
2. Set all environment variables from `.env.example` in the Railway dashboard.
3. Push to your linked repository — Railway will run `release: python manage.py migrate` then start Gunicorn via the `Procfile`.

---

## Admin panel

Available at `/admin/`. Create a superuser with `python manage.py createsuperuser`.
