import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

try:
    SECRET_KEY = env("SECRET_KEY")
except ImproperlyConfigured as err:
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable is required. "
        "Generate one with: "
        'python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    ) from err

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Local
    "apps.users",
    "apps.chat",
    "apps.analyzer",
    "apps.ratelimit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.RequestAuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_testing = "test" in sys.argv
DATABASE_URL = env("DATABASE_URL", default="sqlite:///db.sqlite3")

if not DEBUG and not _testing and DATABASE_URL == "sqlite:///db.sqlite3":
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable is required in production. "
        "Set it to a PostgreSQL connection string, e.g. "
        "postgresql://user:password@host:5432/dbname"
    )

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "users.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django 5.1 removed the STATICFILES_STORAGE setting; the staticfiles backend is
# now configured through STORAGES. WhiteNoise serves compressed, hash-manifested
# assets so collectstatic output is cache-busted in production.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Security & SSL ─────────────────────────────────────────────────────────
# Railway terminates TLS at its proxy and forwards the original scheme
# via X-Forwarded-Proto, so Django must trust that header to recognise
# incoming requests as HTTPS. SSL_REDIRECT is left off (Railway's proxy
# already redirects).
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if not DEBUG and not _testing:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # 1 year HSTS — only enabled outside dev/test to avoid pinning HTTPS on
    # localhost. Opt out via SECURE_HSTS_SECONDS=0 in env if needed.
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_HSTS_SECONDS = 0

# ── Cache ──────────────────────────────────────────────────────────────────────
# Throttle counters live in the cache; gunicorn workers MUST share state, so we
# must not use the default per-process LocMemCache in production. Prefer Redis
# when REDIS_URL is set; otherwise fall back to the database cache table
# `django_cache` (created by `python manage.py createcachetable`).
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
elif _testing or DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "nullbreach-dev",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        }
    }

# ── Django REST Framework ──────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "500/hour",
        "anon": "60/hour",
        "auth": "10/min",
        "claude_chat": "60/hour",
        "claude_scan": "20/hour",
    },
}

# ── drf-spectacular ────────────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "NullBreach API",
    "DESCRIPTION": "AI-powered cybersecurity assistant — chat and OWASP vulnerability analysis.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
}

# ── Simple JWT ─────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── CORS ───────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS", default="http://localhost:5173").split(",")
CORS_ALLOW_CREDENTIALS = True

# ── CSRF ───────────────────────────────────────────────────────────────────────
# Django 4+ requires the scheme on trusted origins. Needed for the Django admin
# login when running behind Railway's TLS-terminating proxy; the JWT API itself
# is CSRF-exempt. Defaults to the CORS origins so a single env var covers both.
CSRF_TRUSTED_ORIGINS = env(
    "CSRF_TRUSTED_ORIGINS", default=",".join(CORS_ALLOWED_ORIGINS)
).split(",")

# ── Logging ───────────────────────────────────────────────────────────────────
# `text` formatter is for local development (human-readable). In production
# (DEBUG=False) we emit one JSON object per line so log aggregators
# (Railway, Loki, Datadog) can parse fields without regex.
LOG_FORMATTER = "text" if DEBUG or _testing else "json"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "text": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
        "json": {
            "()": "config.log_formatter.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMATTER,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ── Rate limiting (daily, per-user, DB-backed) ─────────────────────────────────
# Daily per-user request limits, persisted in the RateLimit table (see
# apps/ratelimit). They reset at UTC midnight and are configurable via
# environment variables. Independent of DRF throttling, which lives in the cache.
RATE_LIMITS = {
    "chat_messages": env.int("CHAT_DAILY_LIMIT", default=10),
    "analyzer_scan": env.int("ANALYZER_DAILY_LIMIT", default=5),
}

# ── Anthropic ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

if not DEBUG and not _testing and not ANTHROPIC_API_KEY:
    raise ImproperlyConfigured(
        "ANTHROPIC_API_KEY environment variable is required in production. "
        "Get one at https://console.anthropic.com/ → Settings → API Keys."
    )
