import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

try:
    SECRET_KEY = env("SECRET_KEY")
except ImproperlyConfigured:
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable is required. "
        "Generate one with: "
        'python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )

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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Security & SSL ─────────────────────────────────────────────────────────
# Railway terminates TLS at its proxy and forwards the original scheme
# via X-Forwarded-Proto, so Django must trust that header to recognise
# incoming requests as HTTPS. SSL_REDIRECT is left off (Railway's proxy
# already redirects), and HSTS is disabled for now to keep the deploy flexible.
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 0

if not DEBUG and not _testing:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ── Django REST Framework ──────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "500/hour",
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
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── CORS ───────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env(
    "CORS_ALLOWED_ORIGINS", default="http://localhost:5173"
).split(",")
CORS_ALLOW_CREDENTIALS = True

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
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

# ── Anthropic ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

if not DEBUG and not _testing and not ANTHROPIC_API_KEY:
    raise ImproperlyConfigured(
        "ANTHROPIC_API_KEY environment variable is required in production. "
        "Get one at https://console.anthropic.com/ → Settings → API Keys."
    )
